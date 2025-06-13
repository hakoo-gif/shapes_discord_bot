import asyncio
import logging
import os
import sys
from dotenv import load_dotenv
from core.bot_client import ShapesBot

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def main():
    """Main entry point for the bot"""
    bot = None
    try:
        # Validate required environment variables
        required_vars = ['BOT_TOKEN', 'SHAPES_API_KEY', 'SHAPES_USERNAME']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            return
        
        # Initialize the bot
        bot = ShapesBot()
        
        # Load cogs
        try:
            await bot.load_extension('cogs.ai')
            logger.info("Loaded AI cog successfully")
        except Exception as e:
            logger.error(f"Failed to load AI cog: {e}")
            return
            
        try:
            await bot.load_extension('cogs.commands')
            logger.info("Loaded commands cog successfully")
        except Exception as e:
            logger.error(f"Failed to load commands cog: {e}")
            return
        
        logger.info("Starting Shapes Discord Bot...")
        
        # Start the bot
        token = os.getenv('BOT_TOKEN')
        if not token:
            logger.error("BOT_TOKEN is empty or not set")
            return
            
        await bot.start(token)
        
    except KeyboardInterrupt:
        logger.info("Bot shutdown initiated by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        if bot:
            try:
                await bot.close()
            except Exception as e:
                logger.error(f"Error closing bot: {e}")

if __name__ == "__main__":
    try:
        # Check Python version
        if sys.version_info < (3, 8):
            logger.error("Python 3.8+ is required")
            sys.exit(1)
            
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        sys.exit(1)
