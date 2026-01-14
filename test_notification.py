"""Test script for notification functionality."""
import asyncio
import sys
from bot import bot
from monitor import Monitor
from database import Database
from lego_checker import LEGOChecker
from config import DISCORD_BOT_TOKEN

async def test_notification():
    """Test sending a notification."""
    print("Testing Notification System")
    print("=" * 60)
    
    # Initialize components
    db = Database()
    await db.initialize()
    
    lego_checker = LEGOChecker()
    monitor = Monitor(bot, db, lego_checker, interval_minutes=5)
    
    # You'll need to provide your Discord user ID and optionally a guild ID
    print("\nTo test notifications, you need:")
    print("1. Your Discord User ID (right-click your profile > Copy ID)")
    print("2. Optionally, a Guild/Server ID where you want to test")
    print("\nEnter your Discord User ID (or press Enter to skip):")
    user_input = input().strip()
    
    if not user_input:
        print("Skipping notification test.")
        return
    
    try:
        user_id = int(user_input)
    except ValueError:
        print("Invalid user ID. Must be a number.")
        return
    
    print("\nEnter Guild/Server ID (optional, press Enter to skip):")
    guild_input = input().strip()
    guild_id = int(guild_input) if guild_input else None
    
    print("\nEnter a LEGO set code to test with:")
    set_code = input().strip()
    
    if not set_code:
        print("No set code provided. Skipping.")
        return
    
    # Check stock
    print(f"\nChecking stock for set {set_code}...")
    result = lego_checker.check_stock(set_code)
    
    print(f"\nStock Check Result:")
    print(f"  Set Name: {result['set_name']}")
    print(f"  Status: {result['status']}")
    print(f"  Available: {result['available']}")
    print(f"  Button Detected: {result.get('button_detected', 'None')}")
    
    # Start bot (required for sending messages)
    print("\nStarting bot to send notification...")
    print("Note: Make sure the bot token is set in .env file")
    
    try:
        # Start bot in background
        bot_task = asyncio.create_task(bot.start(DISCORD_BOT_TOKEN))
        
        # Wait a bit for bot to connect
        await asyncio.sleep(3)
        
        if not bot.is_ready:
            print("Bot is not ready yet. Waiting...")
            await asyncio.sleep(2)
        
        # Test status change notification
        print("\nSending status change notification...")
        await monitor._send_notification(
            user_id=user_id,
            guild_id=guild_id,
            set_code=set_code,
            result=result,
            old_status='out_of_stock',
            new_status=result['status']
        )
        
        # Test button notification if button was detected
        if result.get('button_detected'):
            print("\nSending button detection notification...")
            await monitor._send_button_notification(
                user_id=user_id,
                guild_id=guild_id,
                set_code=set_code,
                result=result,
                old_button=None,
                new_button=result['button_detected']
            )
        
        print("\nNotifications sent! Check your Discord.")
        print("Press Ctrl+C to stop the bot...")
        
        # Keep bot running
        await bot_task
        
    except KeyboardInterrupt:
        print("\nStopping bot...")
        await bot.close()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        await bot.close()

if __name__ == '__main__':
    try:
        asyncio.run(test_notification())
    except KeyboardInterrupt:
        print("\nTest cancelled.")

