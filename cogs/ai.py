import os
import re
import io
import json
import logging
import aiohttp
import asyncio
import discord
from discord.ext import commands
from typing import Optional, Dict, Any, List

from utils.auth import AuthManager
from utils.filters import TriggerFilter, MediaProcessor, ResponseProcessor
from utils.limiter import RateLimiter, ResponseScheduler

logger = logging.getLogger(__name__)

class AICog(commands.Cog):
    """Main AI interaction cog using Shapes API"""
    
    def __init__(self, bot):
        self.bot = bot
        self.shapes_api_url = "https://api.shapes.inc/v1/chat/completions"
        
        default_app_id = getattr(bot, 'shapes_app_id', os.getenv('SHAPES_APP_ID', ''))
        self.auth_manager = AuthManager(bot.storage, default_app_id)
        
        # Initialize components
        self.auth_manager = AuthManager(bot.storage, bot.shapes_api_key)
        self.media_processor = MediaProcessor()
        self.trigger_filter = TriggerFilter()
        self.response_processor = ResponseProcessor()
        self.rate_limiter = RateLimiter()
        self.response_scheduler = ResponseScheduler(self.rate_limiter)
        
        # Cache for rate limit info
        self.rate_limit_cache = {}
        
        # Reply style configuration (1=reply with ping, 2=reply no ping, 3=direct message)
        self.reply_style = int(os.getenv('REPLY_STYLE', '1'))
        
        # Custom error message
        self.custom_error_message = os.getenv('ERROR_MESSAGE', '').strip()
        
    async def _check_basic_permissions(self, message: discord.Message) -> bool:
        """Check if bot has basic permissions to operate in the channel"""
        try:
            # Always allow DMs
            if isinstance(message.channel, discord.DMChannel):
                return True
            
            # Check guild permissions
            if message.guild:
                bot_member = message.guild.get_member(self.bot.user.id)
                if not bot_member:
                    return False
                
                # Get channel permissions
                permissions = message.channel.permissions_for(bot_member)
                
                # Check minimum required permissions
                required_perms = [
                    permissions.read_messages,
                    permissions.send_messages,
                    permissions.view_channel
                ]
                
                if not all(required_perms):
                    logger.warning(f"Missing basic permissions in channel {message.channel.id}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking permissions: {e}")
            return False
        
    async def _resolve_user_mentions(self, message: discord.Message, content: str) -> str:
        """
        Resolve user mentions (<@123456789>) to display names
        
        Args:
            message: The Discord message (for guild context)
            content: The message content with mentions
            
        Returns:
            Content with mentions resolved to display names
        """
        try:
            import re
            # Pattern to match user mentions: <@123456789> or <@!123456789>
            mention_pattern = r'<@!?(\d+)>'
            
            def replace_mention(match):
                user_id = int(match.group(1))
                
                # Try to get user from guild first (for display names)
                if message.guild:
                    member = message.guild.get_member(user_id)
                    if member:
                        return f"@{member.display_name}"
                
                # Fallback to bot's user cache
                user = message.guild.get_member(user_id) if message.guild else None
                if not user and hasattr(message, '_state') and message._state:
                    # Try to get from bot's user cache
                    user = message._state.get_user(user_id)
                
                if user:
                    return f"@{user.display_name if hasattr(user, 'display_name') else user.name}"
                
                # Fallback - keep the original mention but make it more readable
                return f"@User({user_id})"
            
            # Replace all mentions
            resolved_content = re.sub(mention_pattern, replace_mention, content)
            return resolved_content
            
        except Exception as e:
            logger.error(f"Error resolving user mentions: {e}")
            # Return original content if error occurs
            return content
        
    async def _can_send_messages(self, channel) -> bool:
        """Check if bot can send messages in the channel"""
        try:
            if isinstance(channel, discord.DMChannel):
                return True
            
            if hasattr(channel, 'guild') and channel.guild:
                bot_member = channel.guild.get_member(self.bot.user.id)
                if not bot_member:
                    return False
                
                permissions = channel.permissions_for(bot_member)
                return permissions.send_messages and permissions.view_channel
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking send permissions: {e}")
            return False
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle incoming messages"""
        try:
            # Ignore bot's own messages
            if message.author == self.bot.user:
                return
            
            # Check if user is blocked
            if message.guild and await self.bot.storage.is_user_blocked(message.guild.id, message.author.id):
                return
            
            # Check basic Discord permissions before proceeding
            if not await self._check_basic_permissions(message):
                return
            
            # Determine if we should respond
            should_respond = await self._should_respond_to_message(message)
            if not should_respond:
                return
            
            # Check if it's a bot conversation
            is_bot_conversation = message.author.bot
            
            if is_bot_conversation:
                # Use scheduler delays for bot conversations
                await self.response_scheduler.schedule_response(
                    message=message,
                    response_func=lambda: self._handle_ai_response(message, is_bot_conversation=True),
                    is_bot_conversation=True
                )
            else:
                try:
                    async with message.channel.typing():
                        await self._handle_ai_response(message, is_bot_conversation=False)
                except discord.Forbidden:
                    # Can't send typing indicator, but still try to respond
                    logger.warning(f"Missing typing permission in {message.channel.id}")
                    await self._handle_ai_response(message, is_bot_conversation=False)
            
        except discord.Forbidden as e:
            logger.warning(f"Discord permission error in {message.channel.id}: {e}")
            return
        except Exception as e:
            logger.error(f"Error in on_message: {e}", exc_info=True)
    
    async def _should_respond_to_message(self, message: discord.Message) -> bool:
        """Determine if bot should respond to a message"""
        try:
            # Always respond in DMs
            if isinstance(message.channel, discord.DMChannel):
                return True
            
            # Check guild settings
            if message.guild:
                settings = await self.bot.storage.get_server_settings(message.guild.id)
                
                # Check channel in blacklist/whitelist
                use_blacklist = settings.get("use_blacklist", False)
                blacklist = settings.get("blacklist", [])
                whitelist = settings.get("whitelist", [])
                
                # Check if channel is restricted
                if use_blacklist:
                    # Ignore blacklisted channels
                    if message.channel.id in blacklist:
                        return False
                else:
                    # Only respond in whitelisted channels
                    if whitelist:  # Only apply whitelist if it has channels
                        if message.channel.id not in whitelist:
                            return False
                
                # Check if specific channel is activated
                is_channel_activated = await self.bot.storage.is_channel_activated(
                    message.guild.id, message.channel.id
                )
                
                # Check mentions and replies
                is_mentioned_or_replied = (
                    self.bot.user in message.mentions or 
                    (message.reference and 
                     message.reference.resolved and 
                     message.reference.resolved.author == self.bot.user)
                )
                
                # Check global trigger words
                has_global_trigger_words = self.trigger_filter.check_trigger_words(
                    message.content, self.bot.trigger_words
                )
                
                # Check server-specific trigger words
                server_trigger_words = await self.bot.storage.get_server_trigger_words(message.guild.id)
                has_server_trigger_words = self.trigger_filter.check_trigger_words(
                    message.content, server_trigger_words
                )
                
                has_trigger_words = has_global_trigger_words or has_server_trigger_words
                
                if is_channel_activated:
                    # Channel is activated - respond to all messages but avoid joining conversations
                    # Don't respond if:
                    # 1. Message is a reply to someone else (not the bot)
                    # 2. AND the message doesn't mention the bot or contain trigger words
                    if (message.reference and 
                        message.reference.resolved and 
                        message.reference.resolved.author != self.bot.user and
                        not is_mentioned_or_replied and 
                        not has_trigger_words):
                        return False
                    
                    return True
                else:
                    # Channel not activated - only respond to mentions and trigger words
                    return is_mentioned_or_replied or has_trigger_words
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking if should respond: {e}")
            return False
    
    async def _handle_ai_response(self, message: discord.Message, is_bot_conversation: bool = False):
        """Handle AI response generation and sending"""
        try:
            # Get user's auth data
            user_auth_data = await self.auth_manager.get_user_auth_data(message.author.id)
            
            # Build message content with media processing
            message_content = message.content or ""
            media_description, media_data = await self.media_processor.process_message_media(message)
            
            # Build current message with consistent format
            current_message_parts = []
            
            # Add reply context if this message is a reply
            if message.reference and message.reference.resolved:
                replied_msg = message.reference.resolved
                replied_content = replied_msg.content or ""
                
                # Process replied message media
                replied_media_description, replied_media_data = await self.media_processor.process_message_media(replied_msg)
                
                # Build replied message text
                replied_text = replied_content
                if replied_media_description:
                    replied_text = f"{replied_text} {replied_media_description}".strip()
                
                # Add reply context with truncation
                replied_text_truncated = replied_text[:50] + "..." if len(replied_text) > 50 else replied_text
                current_message_parts.append(f"[Replying to {replied_msg.author.display_name}: {replied_text_truncated}]")
                
                # Add replied media to media data
                media_data.extend(replied_media_data)
            
            # Add main message content
            if message_content:
                # Resolve user mentions to display names
                message_content = await self._resolve_user_mentions(message, message_content)
                current_message_parts.append(message_content)
            
            # Add media description
            if media_description:
                current_message_parts.append(media_description)
            
            # Combine all parts
            formatted_current_message = " ".join(current_message_parts)
            
            # Determine if user just pinged the bot
            is_ping = (self.bot.user in message.mentions and 
                      not message.content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip())
            
            # Build prompt
            if is_ping and not formatted_current_message.strip():
                prompt = f"{message.author.display_name} is trying to get your attention (they pinged you). If this message is a reply to another message, check the original message to understand what they need."
            elif formatted_current_message:
                prompt = f"{message.author.display_name}: {formatted_current_message}"
            else:
                prompt = f"{message.author.display_name} sent a message."
            
            # Generate AI response
            response_text = await self._generate_ai_response(prompt, message.author.id, user_auth_data, message, media_data, is_bot_conversation)
            
            if response_text:
                await self._send_response(message, response_text, is_bot_conversation)
            elif not is_bot_conversation:
                error_msg = self.custom_error_message if self.custom_error_message else "I'm having trouble generating a response right now. Please try again later."
                await self._send_error_message(message, error_msg)
                
        except Exception as e:
            logger.error(f"Error handling AI response: {e}", exc_info=True)
            if not is_bot_conversation:
                error_msg = self.custom_error_message if self.custom_error_message else "An error occurred while processing your message."
                await self._send_error_message(message, error_msg)

    async def _generate_ai_response(self, prompt: str, user_id: int, user_auth_data: Optional[Dict[str, str]], message: discord.Message, media_data: List[Dict] = None, is_bot_conversation: bool = False) -> Optional[str]:
        """Generate AI response using Shapes API"""
        try:
            # Prepare messages
            messages = [{"role": "user", "content": prompt}]
            
            # Add image data if present
            if media_data:
                for media in media_data:
                    if media.get('type') == 'image_base64':
                        # Add image description prompt
                        image_prompt = f"Please describe this image in detail: [Image: {media.get('filename', 'image')}]"
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": image_prompt},
                                {
                                    "type": "image_url", 
                                    "image_url": {
                                        "url": f"data:{media['mime_type']};base64,{media['data']}"
                                    }
                                }
                            ]
                        })
                    elif media.get('type') == 'audio_url' and media.get('transcription'):
                        messages.append({
                            "role": "user", 
                            "content": f"[Audio transcription: {media['transcription']}]"
                        })
            
            # Prepare headers and rate limit key
            if user_auth_data and user_auth_data.get('app_id') and user_auth_data.get('auth_token'):
                # User has auth data, use their credentials
                headers = self.auth_manager.create_headers_for_user(
                    user_auth_data['app_id'], 
                    user_auth_data['auth_token']
                )
                # Set API key to "not-needed" when using user auth
                headers["Authorization"] = "Bearer not-needed"
                rate_limit_key = f"user_{user_id}"
            else:
                # Default headers for user/channel identification
                headers = {
                    "Authorization": f"Bearer {self.bot.shapes_api_key}",
                    "Content-Type": "application/json",
                    "X-User-Id": str(user_id),
                    "X-Channel-Id": str(message.channel.id)
                }
                rate_limit_key = "default"
            
            # Check rate limits
            if self.rate_limiter.is_api_rate_limited(rate_limit_key):
                wait_time = self.rate_limiter.get_api_rate_limit_wait(rate_limit_key)
                logger.warning(f"Rate limited for {rate_limit_key}, waiting {wait_time:.1f}s")
                
                # Handle rate limit for bot vs human conversations
                if is_bot_conversation:
                    return None
                else:
                    return f"I'm being rate limited. Please try again in {wait_time:.1f} seconds."
            
            # Prepare payload
            payload = {
                "model": f"shapesinc/{self.bot.SHAPES_USERNAME}",
                "messages": messages
            }
            
            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.post(self.shapes_api_url, json=payload, headers=headers) as response:
                    # Handle rate limiting
                    if response.status == 429:
                        reset_time = float(response.headers.get('X-RateLimit-Reset-Time', 0))
                        remaining = int(response.headers.get('X-Ratelimit-Remaining', 0))
                        
                        if reset_time > 0:
                            import time
                            wait_time = reset_time - time.time()
                            self.rate_limiter.set_api_rate_limit(rate_limit_key, reset_time, remaining)
                            
                            # Handle rate limit for bot vs human conversations
                            if is_bot_conversation:
                                return None
                            else:
                                return f"I'm being rate limited. Please try again in {wait_time:.1f} seconds."
                        else:
                            if is_bot_conversation:
                                return None
                            else:
                                return "I'm currently rate limited. Please try again in a moment."
                    
                    # Handle other errors
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Shapes API error {response.status}: {error_text}")
                        
                        if response.status == 401:
                            if user_auth_data:
                                # Remove invalid auth token
                                await self.auth_manager.remove_user_auth_token(user_id)
                                return "Your authentication has expired. Please use `/auth` to re-authenticate."
                            else:
                                return "Authentication error. Please check that your Shapes API key is valid."
                        elif response.status == 403:
                            return "Access forbidden. Please check your permissions."
                        elif response.status == 502:
                            # Bad Gateway - server-side error
                            if is_bot_conversation:
                                return None
                            else:
                                return "The AI service is temporarily unavailable. Please try again in a few moments."
                        elif response.status == 503:
                            # Service Unavailable
                            if is_bot_conversation:
                                return None
                            else:
                                return "The AI service is currently overloaded. Please try again later."
                        elif response.status == 504:
                            # Gateway Timeout
                            if is_bot_conversation:
                                return None
                            else:
                                return "The AI service timed out. Please try again with a shorter message."
                        elif response.status >= 500:
                            # Other 5xx server errors
                            if is_bot_conversation:
                                return None
                            else:
                                return "The AI service is experiencing issues. Please try again later."
                        else:
                            # Other 4xx client errors
                            if is_bot_conversation:
                                return None
                            else:
                                return f"Request error ({response.status}). Please try again later."
                    
                    # Parse successful response
                    data = await response.json()
                    
                    if 'choices' in data and len(data['choices']) > 0:
                        content = data['choices'][0]['message']['content']
                        return content.strip()
                    else:
                        logger.error(f"Unexpected API response format: {data}")
                        return "Received an unexpected response from the API."
                        
        except aiohttp.ClientError as e:
            logger.error(f"Network error calling Shapes API: {e}")
            return "Network error. Please try again later."
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response: {e}")
            return "Failed to parse API response. Please try again later."
        except Exception as e:
            logger.error(f"Error generating AI response: {e}", exc_info=True)
            return "An error occurred while generating the response."
            
    async def _send_error_message(self, original_message: discord.Message, error_msg: str):
        """Send error message to the channel"""
        try:
            await original_message.channel.send(error_msg)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    async def _send_response(self, original_message: discord.Message, response_text: str, is_bot_conversation: bool = False):
        """Send AI response, handling file attachments and message length"""
        try:
            # Check permissions before attempting to send
            if not await self._can_send_messages(original_message.channel):
                logger.warning(f"Cannot send messages in channel {original_message.channel.id}")
                return
            
            # Process response to extract Shapes files
            cleaned_content, shapes_files = self.response_processor.extract_shapes_files(response_text)
            
            # Handle empty content
            if not cleaned_content.strip():
                cleaned_content = "I generated a response with files, but no text content."
            
            # Split long messages
            message_chunks = self.response_processor.split_long_message(cleaned_content, 1900)
            
            # Prepare files for attachment
            files = []
            if shapes_files:
                files = await self._download_shapes_files(shapes_files)
            
            # Send messages
            for i, chunk in enumerate(message_chunks):
                try:
                    # Only attach files to the first message
                    current_files = files if i == 0 else []
                    
                    if isinstance(original_message.channel, discord.DMChannel):
                        # In DMs, always send directly
                        await original_message.channel.send(chunk, files=current_files)
                    else:
                        # In guilds, use reply style configuration
                        if self.reply_style == 1:
                            # Reply with ping (default)
                            await original_message.reply(chunk, files=current_files, mention_author=True)
                        elif self.reply_style == 2:
                            # Reply without ping
                            await original_message.reply(chunk, files=current_files, mention_author=False)
                        elif self.reply_style == 3:
                            # Send direct message to channel
                            await original_message.channel.send(chunk, files=current_files)
                        else:
                            # Fallback to default (reply with ping)
                            await original_message.reply(chunk, files=current_files, mention_author=True)
                    
                    # Small delay between messages to avoid spam
                    if len(message_chunks) > 1 and i < len(message_chunks) - 1:
                        await asyncio.sleep(1)
                        
                except discord.Forbidden as e:
                    logger.warning(f"Permission denied sending message in {original_message.channel.id}: {e}")
                    # Try fallback methods
                    try:
                        if current_files:
                            # Try without files first
                            await original_message.channel.send(chunk)
                        else:
                            # Already no files, permission issue is fundamental
                            break
                    except discord.Forbidden:
                        logger.warning(f"Cannot send any messages in {original_message.channel.id}")
                        break
                        
                except discord.HTTPException as e:
                    logger.error(f"Failed to send message chunk {i+1}: {e}")
                    # Try to send without files as fallback
                    if current_files:
                        try:
                            if isinstance(original_message.channel, discord.DMChannel):
                                await original_message.channel.send(chunk)
                            else:
                                # Use same reply style for fallback
                                if self.reply_style == 1:
                                    await original_message.reply(chunk, mention_author=True)
                                elif self.reply_style == 2:
                                    await original_message.reply(chunk, mention_author=False)
                                elif self.reply_style == 3:
                                    await original_message.channel.send(chunk)
                                else:
                                    await original_message.reply(chunk, mention_author=True)
                        except (discord.HTTPException, discord.Forbidden):
                            logger.error(f"Failed to send message chunk {i+1} even without files")
            
        except discord.Forbidden as e:
            logger.warning(f"Permission error sending response: {e}")
            return
        except Exception as e:
            logger.error(f"Error sending response: {e}", exc_info=True)
            if not is_bot_conversation:
                error_msg = self.custom_error_message if self.custom_error_message else "I generated a response but couldn't send it properly."
                await self._send_error_message(original_message, error_msg)
    
    async def _download_shapes_files(self, file_urls: List[str]) -> List[discord.File]:
        """Download Shapes files and convert to Discord files"""
        files = []
        
        for url in file_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            file_data = await response.read()
                            
                            # Try to determine filename from URL
                            filename = url.split('/')[-1]
                            if not filename or '.' not in filename:
                                # Try to get from content-disposition header
                                content_disposition = response.headers.get('content-disposition', '')
                                if 'filename=' in content_disposition:
                                    filename = content_disposition.split('filename=')[1].strip('"\'')
                                else:
                                    # Fallback filename based on content type
                                    content_type = response.headers.get('content-type', '')
                                    if 'image' in content_type:
                                        filename = f"image.{content_type.split('/')[-1]}"
                                    elif 'audio' in content_type:
                                        filename = f"audio.{content_type.split('/')[-1]}"
                                    else:
                                        filename = "file"
                            
                            # Create Discord file using io.BytesIO
                            import io
                            discord_file = discord.File(
                                fp=io.BytesIO(file_data),
                                filename=filename
                            )
                            files.append(discord_file)
                            
                        else:
                            logger.error(f"Failed to download file from {url}: HTTP {response.status}")
                            
            except Exception as e:
                logger.error(f"Error downloading file from {url}: {e}")
                continue
        
        return files
    
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle cog-specific command errors"""
        logger.error(f"Command error in AI cog: {error}", exc_info=True)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(AICog(bot))
