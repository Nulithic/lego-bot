"""Configuration management for the LEGO bot."""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Discord Bot Token
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not DISCORD_BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is required")

# Monitoring configuration
MONITOR_INTERVAL_MINUTES = int(os.getenv("MONITOR_INTERVAL_MINUTES", "5"))
RATE_LIMIT_DELAY_SECONDS = float(os.getenv("RATE_LIMIT_DELAY_SECONDS", "2.0"))

# Database file path
DATABASE_PATH = os.getenv("DATABASE_PATH", "lego_bot.db")

