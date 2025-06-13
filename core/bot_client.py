import os
import logging
import discord
from discord.ext import commands
from utils.storage import DataStorage

logger = logging.getLogger(__name__)

class ShapesBot(commands.Bot):
    """Custom Discord bot class for Shapes integration"""
    
    def __init__(self):
        # Configure bot intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        # Configure activity
        activity_type = os.getenv('ACTIVITY_TYPE', 'none').lower()
        activity_message = os.getenv('ACTIVITY_MESSAGE', '')
        status_str = os.getenv('STATUS', 'online').lower()
        
        activity = None
        if activity_type != 'none' and activity_message:
            if activity_type == 'custom':
                activity = discord.CustomActivity(name=activity_message)
            elif activity_type == 'watching':
                activity = discord.Activity(type=discord.ActivityType.watching, name=activity_message)
            elif activity_type == 'listening':
                activity = discord.Activity(type=discord.ActivityType.listening, name=activity_message)
            elif activity_type == 'playing':
                activity = discord.Activity(type=discord.ActivityType.playing, name=activity_message)
            elif activity_type == 'streaming':
                activity = discord.Activity(type=discord.ActivityType.streaming, name=activity_message)
            elif activity_type == 'competing':
                activity = discord.Activity(type=discord.ActivityType.competing, name=activity_message)
        
        status = getattr(discord.Status, status_str, discord.Status.online)
        
        super().__init__(
            command_prefix=None,
            intents=intents,
            activity=activity,
            status=status,
            help_command=None
        )
        
        # Initialize data storage
        try:
            self.storage = DataStorage()
            logger.info("DataStorage initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DataStorage: {e}")
            raise
        
        # Bot configuration
        self.shapes_api_key = os.getenv('SHAPES_API_KEY')
        self.SHAPES_USERNAME = os.getenv('SHAPES_USERNAME')
        self.trigger_words = [word.strip().lower() for word in os.getenv('TRIGGER_WORDS', '').split(',') if word.strip()]
        bot_owner_env = os.getenv('BOT_OWNER')
        try:
            self.bot_owner_id = int(bot_owner_env) if bot_owner_env else None
        except ValueError:
            self.bot_owner_id = None
        
        # Debug logging
        logger.info(f"Bot configuration:")
        logger.info(f"  - API Key configured: {'Yes' if self.shapes_api_key else 'No'}")
        logger.info(f"  - Username: {self.SHAPES_USERNAME}")
        logger.info(f"  - Owner ID: {self.bot_owner_id}")
        logger.info(f"  - Trigger words: {self.trigger_words}")
    
    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info("=" * 50)
        logger.info("BOT IS READY!")
        logger.info(f"Logged in as: {self.user}")
        logger.info(f"User ID: {self.user.id}")
        logger.info(f"Connected to {len(self.guilds)} guilds:")
        
        for guild in self.guilds:
            logger.info(f"  - {guild.name} (ID: {guild.id}, Members: {guild.member_count})")
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
        
        logger.info("=" * 50)
    
    async def on_guild_join(self, guild):
        """Called when bot joins a guild"""
        logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")
        
    async def on_guild_remove(self, guild):
        """Called when bot leaves a guild"""
        logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
    
    async def on_connect(self):
        """Called when bot connects to Discord"""
        logger.info("Bot connected to Discord")
    
    async def on_disconnect(self):
        """Called when bot disconnects from Discord"""
        logger.warning("Bot disconnected from Discord")
    
    async def on_resumed(self):
        """Called when bot resumes connection"""
        logger.info("Bot resumed connection")
    
    async def on_error(self, event, *args, **kwargs):
        """Global error handler"""
        logger.error(f"Error in event {event}", exc_info=True)
    
    """async def on_command_error(self, ctx, error):
        "Command error handler"
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)"""
    
    async def process_commands(self, message):
        # Do nothing
        pass
    
    async def close(self):
        """Clean shutdown"""
        logger.info("Shutting down bot...")
        try:
            await super().close()
            logger.info("Bot shutdown completed")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
