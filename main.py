"""Main entry point for the LEGO Stock Checker Discord Bot."""
import asyncio
import logging
import sys
from bot import bot
from monitor import Monitor
from config import DISCORD_BOT_TOKEN, MONITOR_INTERVAL_MINUTES

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('lego_bot.log')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Main function to start the bot and monitoring."""
    try:
        # Initialize database (bot's setup_hook will also initialize, but this ensures it's ready)
        await bot.db.initialize()
        
        # Initialize monitor (will be started in bot's on_ready event)
        monitor = Monitor(bot, bot.db, bot.lego_checker, MONITOR_INTERVAL_MINUTES)
        bot.monitor = monitor  # Store reference for cleanup and starting
        
        # Start the bot (monitor will start in on_ready event)
        logger.info("Starting Discord bot...")
        await bot.start(DISCORD_BOT_TOKEN)
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        if hasattr(bot, 'monitor'):
            await bot.monitor.stop()
        await bot.close()
        logger.info("Bot shut down complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        sys.exit(1)

