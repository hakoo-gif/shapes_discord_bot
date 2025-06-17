import discord
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class ContextManager:
    """Manages conversation context for the bot"""
    
    MAX_CONTEXT_MESSAGES = 10
    COMMAND_WORDS = ['!help', '!wack', '!reset', '!sleep', '!info', '!dashboard', '!imagine', '!web']
    
    @staticmethod
    async def get_channel_context(channel: discord.TextChannel, 
                                bot_user_id: int,
                                target_message: Optional[discord.Message] = None,
                                media_processor = None) -> List[Dict[str, Any]]:
        """
        Get the last 10 messages from a channel to build context
        
        Args:
            channel: The Discord channel
            bot_user_id: The bot's user ID
            target_message: The message being responded to (optional)
            media_processor: MediaProcessor instance for processing media (optional)
        
        Returns:
            List of message dictionaries for context
        """
        try:
            messages = []
            
            # Get recent messages from the channel
            async for message in channel.history(limit=ContextManager.MAX_CONTEXT_MESSAGES + 5):
                # Skip bot's own messages unless they're part of conversation
                if message.author.id == bot_user_id:
                    continue
                
                # Process message content
                content = await ContextManager._process_message_content(message, media_processor)
                if not content:
                    continue
                
                # Add message to context
                messages.append({
                    'role': 'user',
                    'content': content,
                    'author': message.author.display_name,
                    'author_id': str(message.author.id),
                    'timestamp': message.created_at.isoformat(),
                    'is_target': target_message and message.id == target_message.id
                })
                
                # Stop if we have enough context messages
                if len(messages) >= ContextManager.MAX_CONTEXT_MESSAGES:
                    break
            
            # Reverse to get chronological order (oldest first)
            messages.reverse()
            
            return messages
            
        except Exception as e:
            logger.error(f"Error getting channel context: {e}")
            return []
    
    @staticmethod
    async def _process_message_content(message: discord.Message, media_processor = None) -> str:
        """
        Process a Discord message to extract text content
        
        Args:
            message: The Discord message
            media_processor: MediaProcessor instance for processing media
            
        Returns:
            Processed text content
        """
        content_parts = []
        
        # Add main message content
        if message.content:
            # Process command words - remove "!" prefix
            processed_content = message.content
            for command in ContextManager.COMMAND_WORDS:
                if command in processed_content:
                    processed_content = processed_content.replace(command, command[1:])
            content_parts.append(processed_content)
        
        # Process media if media_processor is available
        if media_processor:
            try:
                media_description, _ = await media_processor.process_message_media(message)
                if media_description:
                    content_parts.append(media_description)
            except Exception as e:
                logger.error(f"Error processing media in context: {e}")
                # Fallback to basic media labeling
                await ContextManager._add_basic_media_labels(message, content_parts)
        else:
            # Fallback to basic media labeling
            await ContextManager._add_basic_media_labels(message, content_parts)
        
        # Handle embeds
        if message.embeds:
            for embed in message.embeds:
                if embed.title:
                    content_parts.append(f"[Embed: {embed.title}]")
                elif embed.description:
                    desc = embed.description[:100] + "..." if len(embed.description) > 100 else embed.description
                    content_parts.append(f"[Embed: {desc}]")
        
        # Handle message references (replies)
        if message.reference and message.reference.message_id:
            try:
                referenced_msg = await message.channel.fetch_message(message.reference.message_id)
                if referenced_msg:
                    ref_content = referenced_msg.content[:50] + "..." if len(referenced_msg.content) > 50 else referenced_msg.content
                    # Process command words in referenced content too
                    for command in ContextManager.COMMAND_WORDS:
                        if command in ref_content:
                            ref_content = ref_content.replace(command, command[1:])
                    
                    # Process media in referenced message if media_processor is available
                    if media_processor:
                        try:
                            ref_media_description, _ = await media_processor.process_message_media(referenced_msg)
                            if ref_media_description:
                                ref_content = f"{ref_content} {ref_media_description}".strip()
                        except Exception as e:
                            logger.error(f"Error processing referenced message media: {e}")
                    
                    content_parts.insert(0, f"[Replying to {referenced_msg.author.display_name}: {ref_content}]")
            except:
                content_parts.insert(0, "[Replying to a message]")
        
        return " ".join(content_parts)
    
    @staticmethod
    async def _add_basic_media_labels(message: discord.Message, content_parts: List[str]):
        """Add basic media labels when media processor is not available"""
        # Handle attachments
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type:
                    if attachment.content_type.startswith('image/'):
                        content_parts.append(f"[Image: {attachment.filename}]")
                    elif attachment.content_type.startswith('audio/'):
                        content_parts.append(f"[Audio: {attachment.filename}]")
                    elif attachment.content_type.startswith('video/'):
                        content_parts.append(f"[Video: {attachment.filename}]")
                    else:
                        content_parts.append(f"[File: {attachment.filename}]")
        
        # Handle stickers
        if message.stickers:
            for sticker in message.stickers:
                content_parts.append(f"[Sticker: {sticker.name}]")
    
    @staticmethod
    def build_prompt(context_messages: List[Dict[str, Any]], 
                    current_message: str,
                    current_user: str,
                    current_user_id: str,
                    is_ping: bool = False) -> str:
        """
        Build a prompt from context and current message
        
        Args:
            context_messages: List of context messages
            current_message: The current message content
            current_user: Display name of current user
            current_user_id: User ID of current user
            is_ping: Whether the bot was pinged/mentioned
            
        Returns:
            Formatted prompt string
        """
        try:
            prompt_parts = []
            
            # Add context if possible
            if context_messages:
                prompt_parts.append("=== Recent conversation context ===")
                for msg in context_messages:
                    if msg.get('is_target'):
                        continue  # Skip the target message as it will be added separately
                    prompt_parts.append(f"{msg['author']}: {msg['content']}")
                prompt_parts.append("=== End context ===\n")
                
                # Add instruction to focus on the last message
                prompt_parts.append("IMPORTANT: Only respond to the most recent message below, not to the context messages above.\n")
            
            # Handle different message scenarios
            if is_ping and not current_message.strip():
                # User just pinged the bot with no message
                prompt_parts.append(f"{current_user} is trying to get your attention (they pinged you). If this message is a reply to another message, check the original message to understand what they need.")
            elif current_message:
                # Regular message
                prompt_parts.append(f"{current_user}: {current_message}")
            else:
                # Fallback
                prompt_parts.append(f"{current_user} sent a message.")
            
            return "\n".join(prompt_parts)
            
        except Exception as e:
            logger.error(f"Error building prompt: {e}")
            # Fallback to simple prompt
            return f"{current_user}: {current_message}" if current_message else f"{current_user} sent a message."