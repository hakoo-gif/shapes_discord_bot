import time
import asyncio
import logging
from typing import Dict, List, Tuple
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class RateLimiter:
    """Handles rate limiting for bot interactions"""
    
    def __init__(self):
        # Bot-to-bot interaction limits (responses per minute)
        self.bot_interactions: Dict[int, deque] = defaultdict(deque)  # channel_id -> timestamps
        self.bot_response_limit = 20
        self.bot_time_window = 60  # seconds
        
        # API rate limit tracking
        self.api_rate_limits: Dict[str, Tuple[float, int]] = {}  # key -> (reset_time, remaining)
        
        # Delay tracking for bot conversations
        self.last_bot_response: Dict[int, float] = {}  # channel_id -> timestamp
        self.bot_delay_min = 10  # minimum delay in seconds
        self.bot_delay_max = 30  # maximum delay in seconds
    
    def can_respond_to_bot(self, channel_id: int) -> Tuple[bool, float]:
        """
        Check if bot can respond to another bot
        
        Args:
            channel_id: The channel ID where the interaction is happening
            
        Returns:
            Tuple of (can_respond, delay_seconds)
        """
        current_time = time.time()
        
        # Clean old entries
        self._cleanup_old_entries(channel_id, current_time)
        
        # Check if we've hit the response limit
        if len(self.bot_interactions[channel_id]) >= self.bot_response_limit:
            # Calculate when we can respond again
            oldest_response = self.bot_interactions[channel_id][0]
            reset_time = oldest_response + self.bot_time_window
            wait_time = max(0, reset_time - current_time)
            return False, wait_time
        
        # Check minimum delay since last response
        if channel_id in self.last_bot_response:
            time_since_last = current_time - self.last_bot_response[channel_id]
            if time_since_last < self.bot_delay_min:
                wait_time = self.bot_delay_min - time_since_last
                return False, wait_time
        
        return True, 0
    
    def record_bot_response(self, channel_id: int):
        """Record that the bot responded to another bot"""
        current_time = time.time()
        self.bot_interactions[channel_id].append(current_time)
        self.last_bot_response[channel_id] = current_time
        
        # Clean old entries
        self._cleanup_old_entries(channel_id, current_time)
    
    def _cleanup_old_entries(self, channel_id: int, current_time: float):
        """Remove entries older than the time window"""
        interactions = self.bot_interactions[channel_id]
        while interactions and interactions[0] < current_time - self.bot_time_window:
            interactions.popleft()
    
    def set_api_rate_limit(self, key: str, reset_time: float, remaining: int):
        """Set API rate limit information"""
        self.api_rate_limits[key] = (reset_time, remaining)
    
    def get_api_rate_limit_wait(self, key: str) -> float:
        """Get how long to wait for API rate limit to reset"""
        if key not in self.api_rate_limits:
            return 0
        
        reset_time, remaining = self.api_rate_limits[key]
        if remaining > 0:
            return 0
        
        current_time = time.time()
        return max(0, reset_time - current_time)
    
    def is_api_rate_limited(self, key: str) -> bool:
        """Check if API is currently rate limited"""
        return self.get_api_rate_limit_wait(key) > 0

class DelayCalculator:
    """Calculates appropriate delays for bot responses"""
    
    @staticmethod
    def get_bot_conversation_delay() -> float:
        """Get random delay for bot-to-bot conversations (10-30 seconds)"""
        import random
        return random.uniform(10, 30)
    
    @staticmethod
    def get_typing_delay(message_length: int) -> float:
        """Calculate typing indicator delay based on message length"""
        # Simulate human typing speed: ~200 characters per minute
        base_delay = message_length / 200 * 60  # Convert to seconds
        
        # Add some randomness and ensure minimum/maximum delays
        import random
        randomized_delay = base_delay * random.uniform(0.8, 1.2)
        
        # Clamp between 1 and 8 seconds
        return max(1, min(8, randomized_delay))

class ResponseScheduler:
    """Schedules bot responses with appropriate delays"""
    
    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter
        self.pending_tasks: Dict[str, asyncio.Task] = {}  # "channel_id:user_id" -> task
        self.latest_bot_message: Dict[str, int] = {}  # "channel_id:user_id" -> message_id
    
    async def schedule_response(self, message, response_func, is_bot_conversation: bool = False):
        """
        Schedule a response with appropriate delay
        
        Args:
            message: Discord message object
            response_func: Async function to call for the response
            is_bot_conversation: Whether this is a bot-to-bot conversation
        """
        channel_id = message.channel.id
        user_id = message.author.id
        message_id = message.id
        
        # Create unique key for this bot in this channel
        bot_key = f"{channel_id}:{user_id}"
        
        if is_bot_conversation:
            # Update latest bot message for this specific bot in this channel
            self.latest_bot_message[bot_key] = message_id
            
            # Cancel any pending response for this specific bot
            if bot_key in self.pending_tasks:
                self.pending_tasks[bot_key].cancel()
                logger.debug(f"Cancelled previous response task for bot {user_id} in channel {channel_id}")
            
            # Check if can respond (channel-wide rate limit)
            can_respond, wait_time = self.rate_limiter.can_respond_to_bot(channel_id)
            if not can_respond:
                logger.info(f"Bot conversation rate limited in channel {channel_id}, wait time: {wait_time:.1f}s")
                return
            
            delay = DelayCalculator.get_bot_conversation_delay()
        else:
            # For human conversations, use channel-only key for backwards compatibility
            human_key = str(channel_id)
            if human_key in self.pending_tasks:
                self.pending_tasks[human_key].cancel()
            delay = 0
            bot_key = human_key
        
        # Checks if message is still latest for this bot
        async def validated_response():
            # For bot conversations, check if this message is still the latest from this bot
            if is_bot_conversation:
                current_latest = self.latest_bot_message.get(f"{channel_id}:{user_id}")
                if current_latest != message_id:
                    logger.debug(f"Skipping response to outdated message {message_id} from bot {user_id} in channel {channel_id} (latest: {current_latest})")
                    return
            
            await response_func()
        
        # Schedule the response
        task = asyncio.create_task(self._delayed_response(message, validated_response, delay, is_bot_conversation))
        self.pending_tasks[bot_key] = task
        
        try:
            await task
        except asyncio.CancelledError:
            logger.debug(f"Response cancelled for {bot_key}")
        finally:
            if bot_key in self.pending_tasks and self.pending_tasks[bot_key] == task:
                del self.pending_tasks[bot_key]
    
    async def _delayed_response(self, message, response_func, delay: float, is_bot_conversation: bool):
        """Execute delayed response"""
        if delay > 0:
            # logger.info(f"Delaying response by {delay:.1f} seconds")
            await asyncio.sleep(delay)
        
        # Show typing indicator for a realistic duration
        async with message.channel.typing():
            # Calculate typing delay (simulate human typing)
            typing_delay = DelayCalculator.get_typing_delay(100)  # Assume ~100 char response
            await asyncio.sleep(typing_delay)
            
            # Execute the response (already validated in schedule_response)
            await response_func()
            
            # Record bot interaction if it's a bot conversation
            if is_bot_conversation:
                self.rate_limiter.record_bot_response(message.channel.id)