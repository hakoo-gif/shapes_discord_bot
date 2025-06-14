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
from core.context import ContextManager

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
                    response_func=lambda: self._handle_ai_response(message),
                    is_bot_conversation=True
                )
            else:
                # Respond to users
                async with message.channel.typing():
                    await self._handle_ai_response(message)
            
        except Exception as e:
            logger.error(f"Error in on_message: {e}", exc_info=True)
    
    async def _should_respond_to_message(self, message: discord.Message) -> bool:
        """Determine if bot should respond to a message"""
        try:
            # Always respond in DMs
            if isinstance(message.channel, discord.DMChannel):
                logger.info(f"DM channel - responding")
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
                
                # Check if bot is activated
                if not settings.get("activated", False):
                    # Bot not activated
                    is_mentioned_or_replied = (
                        self.bot.user in message.mentions or 
                        (message.reference and 
                         message.reference.resolved and 
                         message.reference.resolved.author == self.bot.user)
                    )
                    
                    has_trigger_words = self.trigger_filter.check_trigger_words(message.content, self.bot.trigger_words)
                    
                    result = is_mentioned_or_replied or has_trigger_words
                    return result
                
                # Bot is activated
                return True
            
            logger.info(f"No guild found - not responding")
            return False
            
        except Exception as e:
            logger.error(f"Error checking if should respond: {e}")
            return False
    
    async def _handle_ai_response(self, message: discord.Message):
        """Handle AI response generation and sending"""
        try:
            # Get user's auth data
            user_auth_data = await self.auth_manager.get_user_auth_data(message.author.id)
            
            # Build message content with media processing
            message_content = message.content or ""
            media_description, media_data = await self.media_processor.process_message_media(message)
            
            if media_description:
                message_content = f"{message_content} {media_description}".strip()
            
            # Process replied message media if it exists
            replied_media_description = ""
            replied_media_data = []
            if message.reference and message.reference.resolved:
                replied_msg = message.reference.resolved
                replied_media_description, replied_media_data = await self.media_processor.process_message_media(replied_msg)
                if replied_media_description:
                    message_content = f"{message_content} [Referenced message media: {replied_media_description}]".strip()
            
            # Combine media data
            all_media_data = media_data + replied_media_data
            
            # Build context
            context_messages = await ContextManager.get_channel_context(
                channel=message.channel,
                bot_user_id=self.bot.user.id,
                target_message=message,
                media_processor=self.media_processor  # Pass media processor for context
            )
            
            # Determine if user just pinged the bot
            is_ping = (self.bot.user in message.mentions and 
                      not message.content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip())
            
            # Build prompt
            prompt = ContextManager.build_prompt(
                context_messages=context_messages,
                current_message=message_content,
                current_user=message.author.display_name,
                current_user_id=str(message.author.id),
                is_ping=is_ping
            )
            
            # Generate AI response
            response_text = await self._generate_ai_response(prompt, message.author.id, user_auth_data, message, all_media_data)
            
            if response_text:
                await self._send_response(message, response_text)
            else:
                error_msg = self.custom_error_message if self.custom_error_message else "I'm having trouble generating a response right now. Please try again later."
                await self._send_error_message(message, error_msg)
                
        except Exception as e:
            logger.error(f"Error handling AI response: {e}", exc_info=True)
            error_msg = self.custom_error_message if self.custom_error_message else "An error occurred while processing your message."
            await self._send_error_message(message, error_msg)
            
    async def _send_error_message(self, original_message: discord.Message, error_msg: str):
        """Send error message to the channel"""
        try:
            await original_message.channel.send(error_msg)
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    
    async def _generate_ai_response(self, prompt: str, user_id: int, user_auth_data: Optional[Dict[str, str]], message: discord.Message, media_data: List[Dict] = None) -> Optional[str]:
        """Generate AI response using Shapes API"""
        try:
            # Prepare messages
            messages = [{"role": "user", "content": prompt}]
            
            # Add media data if present
            if media_data:
                for media in media_data:
                    if media.get('type') == 'image_url':
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"[Image: {media.get('filename', 'image')}]"},
                                {"type": "image_url", "image_url": media['image_url']}
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
                            return f"I'm being rate limited. Please try again in {wait_time:.1f} seconds."
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
                        else:
                            return f"API error ({response.status}). Please try again later."
                    
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
    
    async def _send_response(self, original_message: discord.Message, response_text: str):
        """Send AI response, handling file attachments and message length"""
        try:
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
                        except discord.HTTPException:
                            logger.error(f"Failed to send message chunk {i+1} even without files")
                    
        except Exception as e:
            logger.error(f"Error sending response: {e}", exc_info=True)
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
