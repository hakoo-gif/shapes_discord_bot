import re
import aiohttp
import logging
import discord
from PIL import Image
import io
import speech_recognition as sr
from pydub import AudioSegment
import tempfile
import os
import base64
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class TriggerFilter:
    """Handles trigger word filtering"""
    
    @staticmethod
    def _find_url_ranges(text: str) -> List[tuple]:
        """
        Find all URL ranges in the text
        
        Args:
            text: The text to search for URLs
            
        Returns:
            List of tuples containing (start_index, end_index) for each URL
        """
        # URL regex pattern to catch various URL formats
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+|www\.[^\s<>"{}|\\^`\[\]]+|[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s<>"{}|\\^`\[\]]*)?'
        
        url_ranges = []
        for match in re.finditer(url_pattern, text, re.IGNORECASE):
            url_ranges.append((match.start(), match.end()))
        
        return url_ranges
    
    @staticmethod
    def _is_in_url(position: int, url_ranges: List[tuple]) -> bool:
        """
        Check if a position is within any URL range
        
        Args:
            position: The position to check
            url_ranges: List of URL ranges
            
        Returns:
            True if position is within a URL, False otherwise
        """
        for start, end in url_ranges:
            if start <= position < end:
                return True
        return False
    
    @staticmethod
    def check_trigger_words(message_content: str, trigger_words: List[str]) -> bool:
        """
        Check if message contains any trigger words using regex, ignoring words in URLs
        
        Args:
            message_content: The message content to check
            trigger_words: List of trigger words
            
        Returns:
            True if any trigger word is found (not in a URL), False otherwise
        """
        if not trigger_words or not message_content:
            return False
        
        message_lower = message_content.lower()
        
        # Find all URL ranges in the message
        url_ranges = TriggerFilter._find_url_ranges(message_content)
        
        for trigger_word in trigger_words:
            if not trigger_word:
                continue
                
            trigger_lower = trigger_word.lower()
            # Use regex to match whole words only
            pattern = r'(?<![a-zA-Z0-9])' + re.escape(trigger_lower) + r'(?![a-zA-Z0-9])'
            
            for match in re.finditer(pattern, message_lower):
                # Check if this match is within a URL
                if not TriggerFilter._is_in_url(match.start(), url_ranges):
                    return True
        
        return False

class MediaProcessor:
    """Processes images, audio, and stickers"""
    
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.supported_formats = ['.png', '.jpg', '.jpeg', '.webp', '.gif']
    
    def _is_image(self, attachment):
        """Check if an attachment is a supported image format."""
        return any(attachment.filename.lower().endswith(ext) for ext in self.supported_formats)
    
    async def _process_image_to_base64(self, attachment):
        """Process an image attachment into base64 format."""
        try:
            # Download the image
            image_data = await attachment.read()
            
            # Get the MIME type based on file extension
            file_ext = attachment.filename.lower()
            if file_ext.endswith('.png'):
                mime_type = 'image/png'
            elif file_ext.endswith('.jpg') or file_ext.endswith('.jpeg'):
                mime_type = 'image/jpeg'
            elif file_ext.endswith('.webp'):
                mime_type = 'image/webp'
            elif file_ext.endswith('.gif'):
                mime_type = 'image/gif'
            else:
                # Default mime type if not specifically matched
                mime_type = 'image/jpeg'
            
            # Convert to base64
            base64_data = base64.b64encode(image_data).decode('utf-8')
            
            return {
                'data': base64_data,
                'mime_type': mime_type,
                'filename': attachment.filename
            }
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            return None
    
    async def _process_image_url_to_base64(self, url: str):
        """Process an image URL into base64 format."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        # Get filename and determine MIME type
                        filename = url.split('/')[-1] or "image"
                        file_ext = filename.lower()
                        
                        if file_ext.endswith('.png'):
                            mime_type = 'image/png'
                        elif file_ext.endswith('.jpg') or file_ext.endswith('.jpeg'):
                            mime_type = 'image/jpeg'
                        elif file_ext.endswith('.webp'):
                            mime_type = 'image/webp'
                        elif file_ext.endswith('.gif'):
                            mime_type = 'image/gif'
                        else:
                            mime_type = 'image/jpeg'
                        
                        # Convert to base64
                        base64_data = base64.b64encode(image_data).decode('utf-8')
                        
                        return {
                            'data': base64_data,
                            'mime_type': mime_type,
                            'filename': filename
                        }
        except Exception as e:
            logger.error(f"Error processing image URL {url}: {e}")
            return None
    
    async def process_message_media(self, message: discord.Message) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Process all media in a message and return text description + media data
        
        Args:
            message: Discord message object
            
        Returns:
            Tuple of (text_description, media_data_list)
        """
        text_parts = []
        media_data = []
        
        # Process attachments
        for attachment in message.attachments:
            try:
                if attachment.content_type:
                    if attachment.content_type.startswith('image/') and self._is_image(attachment):
                        # Process image for API
                        image_base64 = await self._process_image_to_base64(attachment)
                        if image_base64:
                            text_parts.append(f"[Image: {attachment.filename}]")
                            media_data.append({
                                'type': 'image_base64',
                                'data': image_base64['data'],
                                'mime_type': image_base64['mime_type'],
                                'filename': image_base64['filename']
                            })
                        else:
                            text_parts.append(f"[Image: {attachment.filename} (failed to process)]")
                    
                    elif attachment.content_type.startswith('audio/'):
                        text, data = await self._process_audio_attachment(attachment)
                        if text:
                            text_parts.append(text)
                        if data:
                            media_data.append(data)
                    
                    elif attachment.content_type.startswith('video/'):
                        text_parts.append(f"[Video file: {attachment.filename}]")
                        media_data.append({
                            'type': 'video',
                            'url': attachment.url,
                            'filename': attachment.filename
                        })
            except Exception as e:
                logger.error(f"Error processing attachment {attachment.filename}: {e}")
                text_parts.append(f"[Unable to process {attachment.filename}]")
        
        # Process stickers
        for sticker in message.stickers:
            try:
                text, data = await self._process_sticker(sticker)
                if text:
                    text_parts.append(text)
                if data:
                    media_data.append(data)
            except Exception as e:
                logger.error(f"Error processing sticker {sticker.name}: {e}")
                text_parts.append(f"[Sticker: {sticker.name}]")
        
        # Check for image/audio URLs in message content
        if message.content:
            urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message.content)
            for url in urls:
                try:
                    if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        image_base64 = await self._process_image_url_to_base64(url)
                        if image_base64:
                            text_parts.append(f"[Image from URL: {image_base64['filename']}]")
                            media_data.append({
                                'type': 'image_base64',
                                'data': image_base64['data'],
                                'mime_type': image_base64['mime_type'],
                                'filename': image_base64['filename']
                            })
                        else:
                            text_parts.append(f"[Image from URL (failed to process)]")
                    
                    elif any(ext in url.lower() for ext in ['.mp3', '.wav', '.ogg', '.m4a']):
                        text, data = await self._process_audio_url(url)
                        if text:
                            text_parts.append(text)
                        if data:
                            media_data.append(data)
                except Exception as e:
                    logger.error(f"Error processing URL {url}: {e}")
        
        return " ".join(text_parts), media_data
    
    async def _process_image_attachment(self, attachment: discord.Attachment) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Process image attachment"""
        try:
            # Download image
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        # Basic image analysis
                        with Image.open(io.BytesIO(image_data)) as img:
                            width, height = img.size
                            format_name = img.format
                            
                        description = f"[Image: {attachment.filename} ({width}x{height}, {format_name})]"
                        
                        return description, {
                            'type': 'image_url',
                            'image_url': {'url': attachment.url},
                            'filename': attachment.filename,
                            'size': f"{width}x{height}",
                            'format': format_name
                        }
        except Exception as e:
            logger.error(f"Error processing image {attachment.filename}: {e}")
        
        return f"[Image: {attachment.filename}]", None
    
    async def _process_audio_attachment(self, attachment: discord.Attachment) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Process audio attachment"""
        try:
            # Download audio
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        
                        # Try to transcribe audio
                        transcription = await self._transcribe_audio(audio_data, attachment.filename)
                        
                        if transcription:
                            description = f"[Audio message: \"{transcription}\"]"
                        else:
                            description = f"[Audio file: {attachment.filename}]"
                        
                        return description, {
                            'type': 'audio_url',
                            'audio_url': {'url': attachment.url},
                            'filename': attachment.filename,
                            'transcription': transcription
                        }
        except Exception as e:
            logger.error(f"Error processing audio {attachment.filename}: {e}")
        
        return f"[Audio: {attachment.filename}]", None
    
    async def _process_sticker(self, sticker: discord.Sticker) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Process Discord sticker"""
        try:
            description = f"[Sticker: {sticker.name}"
            if hasattr(sticker, 'description') and sticker.description:
                description += f" - {sticker.description}"
            description += "]"
            
            # Try to get sticker image if it's available
            sticker_data = None
            if hasattr(sticker, 'url') and sticker.url:
                sticker_data = {
                    'type': 'image_url',
                    'image_url': {'url': sticker.url},
                    'filename': f"{sticker.name}.png",
                    'is_sticker': True,
                    'sticker_name': sticker.name
                }
            
            return description, sticker_data
            
        except Exception as e:
            logger.error(f"Error processing sticker {sticker.name}: {e}")
        
        return f"[Sticker: {sticker.name}]", None
    
    async def _process_image_url(self, url: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Process image URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        with Image.open(io.BytesIO(image_data)) as img:
                            width, height = img.size
                            format_name = img.format
                        
                        filename = url.split('/')[-1] or "image"
                        description = f"[Image from URL: {filename} ({width}x{height})]"
                        
                        return description, {
                            'type': 'image_url',
                            'image_url': {'url': url},
                            'filename': filename,
                            'size': f"{width}x{height}",
                            'format': format_name
                        }
        except Exception as e:
            logger.error(f"Error processing image URL {url}: {e}")
        
        return f"[Image from URL]", None
    
    async def _process_audio_url(self, url: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Process audio URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        filename = url.split('/')[-1] or "audio"
                        
                        transcription = await self._transcribe_audio(audio_data, filename)
                        
                        if transcription:
                            description = f"[Audio from URL: \"{transcription}\"]"
                        else:
                            description = f"[Audio from URL: {filename}]"
                        
                        return description, {
                            'type': 'audio_url', 
                            'audio_url': {'url': url},
                            'filename': filename,
                            'transcription': transcription
                        }
        except Exception as e:
            logger.error(f"Error processing audio URL {url}: {e}")
        
        return f"[Audio from URL]", None
    
    async def _transcribe_audio(self, audio_data: bytes, filename: str) -> Optional[str]:
        """Transcribe audio data to text"""
        try:
            # Create temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_input:
                temp_input.write(audio_data)
                temp_input_path = temp_input.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_wav:
                temp_wav_path = temp_wav.name
            
            try:
                # Convert to WAV format
                audio = AudioSegment.from_file(temp_input_path)
                audio.export(temp_wav_path, format="wav")
                
                # Transcribe using speech_recognition
                with sr.AudioFile(temp_wav_path) as source:
                    audio_data = self.recognizer.record(source)
                    text = self.recognizer.recognize_google(audio_data)
                    return text
                    
            finally:
                # Clean up temporary files
                try:
                    os.unlink(temp_input_path)
                    os.unlink(temp_wav_path)
                except:
                    pass
                    
        except Exception as e:
            logger.debug(f"Audio transcription failed for {filename}: {e}")
            return None

class ResponseProcessor:
    """Processes bot responses to handle Shapes file URLs"""
    
    @staticmethod
    def extract_shapes_files(content: str) -> Tuple[str, List[str]]:
        """
        Extract Shapes file URLs from response content
        
        Args:
            content: Response content
            
        Returns:
            Tuple of (cleaned_content, file_urls)
        """
        shapes_file_pattern = r'https://files\.shapes\.inc/[^\s<>"\')]*'
        shapes_files = re.findall(shapes_file_pattern, content)
        
        # Remove the URLs from content
        cleaned_content = re.sub(shapes_file_pattern, '', content)
        
        # Clean up extra whitespace
        cleaned_content = re.sub(r'[ \t]+', ' ', cleaned_content)
        cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)  
        cleaned_content = cleaned_content.strip()
        
        return cleaned_content, shapes_files
    
    @staticmethod
    def split_long_message(content: str, max_length: int = 2000) -> List[str]:
        """
        Split long messages to fit Discord's character limit
        
        Args:
            content: Message content to split
            max_length: Maximum length per message (default 2000)
            
        Returns:
            List of message chunks
        """
        if len(content) <= max_length:
            return [content]
        
        chunks = []
        current_chunk = ""
        
        # Split by sentences first
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
        for sentence in sentences:
            # If a single sentence is too long, split by words
            if len(sentence) > max_length:
                words = sentence.split()
                temp_sentence = ""
                
                for word in words:
                    if len(temp_sentence + " " + word) > max_length:
                        if temp_sentence:
                            if current_chunk:
                                if len(current_chunk + " " + temp_sentence) <= max_length:
                                    current_chunk += " " + temp_sentence
                                else:
                                    chunks.append(current_chunk.strip())
                                    current_chunk = temp_sentence
                            else:
                                current_chunk = temp_sentence
                            
                            temp_sentence = word
                        else:
                            # Single word is too long, force split
                            chunks.append(word[:max_length])
                            temp_sentence = word[max_length:]
                    else:
                        temp_sentence += " " + word if temp_sentence else word
                
                if temp_sentence:
                    sentence = temp_sentence
            
            # Add sentence to current chunk
            if len(current_chunk + " " + sentence) <= max_length:
                current_chunk += " " + sentence if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return [chunk for chunk in chunks if chunk.strip()]
