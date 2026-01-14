"""Background monitoring system for watched sets."""
import asyncio
import logging
from typing import Optional
from lego_checker import LEGOChecker
from database import Database
from config import MONITOR_INTERVAL_MINUTES
import discord

logger = logging.getLogger(__name__)


class Monitor:
    """Monitors watched sets and sends notifications on status changes."""
    
    def __init__(self, bot, db: Database, lego_checker: LEGOChecker, interval_minutes: int = MONITOR_INTERVAL_MINUTES):
        """Initialize the monitor.
        
        Args:
            bot: The Discord bot instance
            db: Database instance
            lego_checker: LEGOChecker instance
            interval_minutes: How often to check (in minutes)
        """
        self.bot = bot
        self.db = db
        self.lego_checker = lego_checker
        self.interval_seconds = interval_minutes * 60
        self.running = False
        self.task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the monitoring task."""
        if self.running:
            logger.warning("Monitor is already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Monitor started (checking every {self.interval_seconds / 60} minutes)")
    
    async def stop(self):
        """Stop the monitoring task."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Monitor stopped")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                await self._check_all_watches()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
            
            # Wait for the interval before checking again
            await asyncio.sleep(self.interval_seconds)
    
    async def _check_all_watches(self):
        """Check all watched sets for status changes."""
        watches = await self.db.get_all_watches()
        
        if not watches:
            logger.debug("No watches to check")
            return
        
        logger.info(f"Checking {len(watches)} watched set(s)...")
        
        for watch in watches:
            if not self.running:
                break
            
            try:
                await self._check_watch(watch)
            except Exception as e:
                logger.error(f"Error checking watch {watch.get('id')}: {e}")
    
    async def _check_watch(self, watch: dict):
        """Check a single watch and notify if status or button changed.
        
        Args:
            watch: Dictionary with watch information
        """
        watch_id = watch['id']
        user_id = watch['user_id']
        guild_id = watch['guild_id']
        set_code = watch['set_code']
        last_status = watch['last_status']
        last_button_detected = watch.get('last_button_detected')
        
        # Check current stock status
        result = self.lego_checker.check_stock(set_code)
        current_status = result['status']
        current_button_detected = result.get('button_detected')
        
        # Update the watch record
        await self.db.update_watch_status(watch_id, current_status, result['available'], current_button_detected)
        
        # Check if status changed
        status_changed = last_status is not None and last_status != current_status
        
        # Check if button changed (from None to a button, or from one button to another)
        button_changed = False
        if last_button_detected != current_button_detected:
            # Button appeared (None -> button) or changed
            if last_button_detected is None and current_button_detected is not None:
                button_changed = True
                logger.info(f"Button detected for set {set_code} (user {user_id}): None -> {current_button_detected}")
            elif last_button_detected is not None and current_button_detected != last_button_detected:
                button_changed = True
                logger.info(f"Button changed for set {set_code} (user {user_id}): {last_button_detected} -> {current_button_detected}")
        
        if last_status is None:
            # First check - don't notify, just record
            logger.debug(f"First check for set {set_code} (user {user_id}): {current_status}")
            return
        
        # Send notification if status changed or button appeared/changed
        if status_changed:
            logger.info(f"Status changed for set {set_code} (user {user_id}): {last_status} -> {current_status}")
            await self._send_notification(user_id, guild_id, set_code, result, last_status, current_status)
        elif button_changed:
            # Button appeared or changed - send notification
            logger.info(f"Button change detected for set {set_code} (user {user_id})")
            await self._send_button_notification(user_id, guild_id, set_code, result, last_button_detected, current_button_detected)
        else:
            logger.debug(f"No change for set {set_code} (user {user_id}): {current_status}")
    
    async def _send_notification(self, user_id: int, guild_id: Optional[int], set_code: str, 
                                 result: dict, old_status: str, new_status: str):
        """Send a notification to a user about a status change.
        
        Args:
            user_id: Discord user ID
            guild_id: Optional Discord guild/server ID
            set_code: LEGO set code
            result: Stock check result dictionary
            old_status: Previous status
            new_status: New status
        """
        try:
            user = self.bot.get_user(user_id)
            if not user:
                # Try to fetch user if not in cache
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.NotFound:
                    logger.warning(f"User {user_id} not found, skipping notification")
                    return
                except Exception as e:
                    logger.error(f"Error fetching user {user_id}: {e}")
                    return
            
            # Determine notification message based on status change
            if new_status == 'in_stock' and result['available']:
                title = "✅ Set is Now In Stock!"
                color = 0x00ff00
                message = f"**{result['set_name']}** (Set {set_code}) is now available!"
            elif new_status == 'out_of_stock':
                title = "❌ Set is Out of Stock"
                color = 0xff0000
                message = f"**{result['set_name']}** (Set {set_code}) is now out of stock."
            elif new_status == 'pre_order':
                title = "⏰ Set Available for Pre-Order"
                color = 0xffaa00
                message = f"**{result['set_name']}** (Set {set_code}) is now available for pre-order!"
            else:
                title = "📦 Stock Status Changed"
                color = 0x0099ff
                message = f"**{result['set_name']}** (Set {set_code}) status changed."
            
            embed = discord.Embed(
                title=title,
                description=message,
                color=color,
                url=result['url']
            )
            
            embed.add_field(name="Previous Status", value=old_status.replace('_', ' ').title(), inline=True)
            embed.add_field(name="Current Status", value=new_status.replace('_', ' ').title(), inline=True)
            
            if result['price']:
                embed.add_field(name="Price", value=result['price'], inline=False)
            
            # Add button detected information if available
            if result.get('button_detected'):
                button_text = result['button_detected']
                button_lower = button_text.lower()
                
                # Choose emoji based on button type
                if 'pre-order' in button_lower or 'preorder' in button_lower:
                    emoji = "⏰"  # Clock for pre-order
                elif 'add to bag' in button_lower or 'add to cart' in button_lower:
                    emoji = "🛒"  # Shopping cart for add to bag/cart
                elif 'notify' in button_lower:
                    emoji = "🔔"  # Bell for notify
                elif 'out of stock' in button_lower or 'sold out' in button_lower:
                    emoji = "❌"  # X for out of stock
                else:
                    emoji = "🔘"  # Default button emoji
                
                embed.add_field(
                    name=f"{emoji} Button Detected", 
                    value=f"```\n{button_text}\n```", 
                    inline=False
                )
            
            embed.set_footer(text="LEGO.com")
            
            # Check if server has a notification channel set
            notification_sent = False
            if guild_id:
                notification_channel_id = await self.db.get_notification_channel(guild_id)
                if notification_channel_id:
                    try:
                        channel = self.bot.get_channel(notification_channel_id)
                        if channel and channel.permissions_for(channel.guild.me).send_messages:
                            await channel.send(f"<@{user_id}>", embed=embed)
                            logger.info(f"Sent notification to user {user_id} in channel {notification_channel_id} for set {set_code}")
                            notification_sent = True
                        else:
                            logger.warning(f"Notification channel {notification_channel_id} not accessible, falling back to DM")
                    except Exception as e:
                        logger.error(f"Error sending to notification channel: {e}")
            
            # If no notification channel or it failed, try DM
            if not notification_sent:
                try:
                    await user.send(embed=embed)
                    logger.info(f"Sent notification to user {user_id} via DM for set {set_code}")
                except discord.Forbidden:
                    # User has DMs disabled, try to send in guild if available
                    if guild_id:
                        try:
                            guild = self.bot.get_guild(guild_id)
                            if guild:
                                # Try to find a channel we can send to
                                for channel in guild.text_channels:
                                    if channel.permissions_for(guild.me).send_messages:
                                        await channel.send(f"<@{user_id}>", embed=embed)
                                        logger.info(f"Sent notification to user {user_id} in guild {guild_id} for set {set_code}")
                                        break
                                else:
                                    logger.warning(f"Could not send notification to user {user_id} - no accessible channels")
                        except Exception as e:
                            logger.error(f"Error sending notification in guild: {e}")
                    else:
                        logger.warning(f"Could not send notification to user {user_id} - DMs disabled and no guild")
                except Exception as e:
                    logger.error(f"Error sending notification to user {user_id}: {e}")
                
        except Exception as e:
            logger.error(f"Unexpected error in _send_notification: {e}")
    
    async def _send_button_notification(self, user_id: int, guild_id: Optional[int], set_code: str, 
                                       result: dict, old_button: Optional[str], new_button: Optional[str]):
        """Send a notification to a user about a button detection change.
        
        Args:
            user_id: Discord user ID
            guild_id: Optional Discord guild/server ID
            set_code: LEGO set code
            result: Stock check result dictionary
            old_button: Previous button text (or None)
            new_button: New button text (or None)
        """
        try:
            user = self.bot.get_user(user_id)
            if not user:
                # Try to fetch user if not in cache
                try:
                    user = await self.bot.fetch_user(user_id)
                except discord.NotFound:
                    logger.warning(f"User {user_id} not found, skipping button notification")
                    return
                except Exception as e:
                    logger.error(f"Error fetching user {user_id}: {e}")
                    return
            
            # Determine notification message based on button change
            if old_button is None and new_button is not None:
                title = "🔘 Button Detected!"
                color = 0x0099ff
                message = f"**{result['set_name']}** (Set {set_code}) now has a button available!"
            elif old_button is not None and new_button != old_button:
                title = "🔘 Button Changed"
                color = 0x0099ff
                message = f"**{result['set_name']}** (Set {set_code}) button has changed."
            else:
                return  # No significant change
            
            embed = discord.Embed(
                title=title,
                description=message,
                color=color,
                url=result['url']
            )
            
            if old_button:
                embed.add_field(name="Previous Button", value=old_button, inline=True)
            else:
                embed.add_field(name="Previous Button", value="None", inline=True)
            
            if new_button:
                # Choose emoji based on button type
                button_lower = new_button.lower()
                if 'pre-order' in button_lower or 'preorder' in button_lower:
                    emoji = "⏰"
                elif 'add to bag' in button_lower or 'add to cart' in button_lower:
                    emoji = "🛒"
                elif 'notify' in button_lower:
                    emoji = "🔔"
                elif 'out of stock' in button_lower or 'sold out' in button_lower:
                    emoji = "❌"
                else:
                    emoji = "🔘"
                
                embed.add_field(
                    name=f"{emoji} Current Button", 
                    value=f"```\n{new_button}\n```", 
                    inline=False
                )
            else:
                embed.add_field(name="Current Button", value="None", inline=True)
            
            embed.add_field(name="Status", value=result['status'].replace('_', ' ').title(), inline=True)
            
            if result['price']:
                embed.add_field(name="Price", value=result['price'], inline=False)
            
            embed.set_footer(text="LEGO.com")
            
            # Check if server has a notification channel set
            notification_sent = False
            if guild_id:
                notification_channel_id = await self.db.get_notification_channel(guild_id)
                if notification_channel_id:
                    try:
                        channel = self.bot.get_channel(notification_channel_id)
                        if channel and channel.permissions_for(channel.guild.me).send_messages:
                            await channel.send(f"<@{user_id}>", embed=embed)
                            logger.info(f"Sent button notification to user {user_id} in channel {notification_channel_id} for set {set_code}")
                            notification_sent = True
                        else:
                            logger.warning(f"Notification channel {notification_channel_id} not accessible, falling back to DM")
                    except Exception as e:
                        logger.error(f"Error sending to notification channel: {e}")
            
            # If no notification channel or it failed, try DM
            if not notification_sent:
                try:
                    await user.send(embed=embed)
                    logger.info(f"Sent button notification to user {user_id} via DM for set {set_code}")
                except discord.Forbidden:
                    # User has DMs disabled, try to send in guild if available
                    if guild_id:
                        try:
                            guild = self.bot.get_guild(guild_id)
                            if guild:
                                # Try to find a channel we can send to
                                for channel in guild.text_channels:
                                    if channel.permissions_for(guild.me).send_messages:
                                        await channel.send(f"<@{user_id}>", embed=embed)
                                        logger.info(f"Sent button notification to user {user_id} in guild {guild_id} for set {set_code}")
                                        break
                                else:
                                    logger.warning(f"Could not send button notification to user {user_id} - no accessible channels")
                        except Exception as e:
                            logger.error(f"Error sending button notification in guild: {e}")
                    else:
                        logger.warning(f"Could not send button notification to user {user_id} - DMs disabled and no guild")
                except Exception as e:
                    logger.error(f"Error sending button notification to user {user_id}: {e}")
                
        except Exception as e:
            logger.error(f"Unexpected error in _send_button_notification: {e}")

