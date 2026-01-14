"""Discord bot implementation."""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional
from lego_checker import LEGOChecker
from database import Database

logger = logging.getLogger(__name__)


class LEGOBot(commands.Bot):
    """Discord bot for checking LEGO stock."""
    
    def __init__(self, command_prefix: str = "!", intents: discord.Intents = None):
        """Initialize the bot.
        
        Args:
            command_prefix: Command prefix (not used for slash commands)
            intents: Discord intents
        """
        if intents is None:
            intents = discord.Intents.default()
            intents.message_content = True
        
        super().__init__(command_prefix=command_prefix, intents=intents)
        
        self.lego_checker = LEGOChecker()
        self.db = Database()
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        await self.db.initialize()
        logger.info("Bot setup complete")
    
    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f"{self.user} has logged in")
        try:
            # Sync to all guilds (instant, no duplicates)
            synced_count = 0
            for guild in self.guilds:
                try:
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    synced_count += len(synced)
                    logger.info(f"Synced {len(synced)} command(s) to guild {guild.name} ({guild.id})")
                except Exception as e:
                    logger.warning(f"Failed to sync commands to guild {guild.name}: {e}")
            
            if synced_count > 0:
                logger.info(f"Total: Synced {synced_count} command(s) to {len(self.guilds)} guild(s)")
            else:
                logger.info("No guilds found to sync commands to")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
        
        # Start monitor if it exists
        if hasattr(self, 'monitor'):
            await self.monitor.start()
    
    def get_status_color(self, status: str) -> int:
        """Get the embed color for a stock status.
        
        Args:
            status: The stock status string
            
        Returns:
            Discord color integer
        """
        status_colors = {
            'in_stock': 0x00ff00,  # Green
            'out_of_stock': 0xff0000,  # Red
            'pre_order': 0xffaa00,  # Orange
            'unknown': 0x808080,  # Gray
            'error': 0xff0000,  # Red
        }
        return status_colors.get(status, 0x808080)
    
    def get_status_emoji(self, status: str, available: bool) -> str:
        """Get an emoji for a stock status.
        
        Args:
            status: The stock status string
            available: Whether the set is available
            
        Returns:
            Emoji string
        """
        if status == 'in_stock' and available:
            return '✅'
        elif status == 'out_of_stock':
            return '❌'
        elif status == 'pre_order':
            return '⏰'
        elif status == 'error':
            return '⚠️'
        else:
            return '❓'


# Create bot instance
bot = LEGOBot()


@bot.tree.command(name="check-stock", description="Check the stock status of a LEGO set")
@app_commands.describe(set_code="The LEGO set code (e.g., 10312)")
async def check_stock(interaction: discord.Interaction, set_code: str):
    """Check stock status for a LEGO set."""
    await interaction.response.defer()
    
    try:
        result = bot.lego_checker.check_stock(set_code)
        
        embed = discord.Embed(
            title=f"{bot.get_status_emoji(result['status'], result['available'])} {result['set_name']}",
            description=f"**Status:** {result['message']}",
            color=bot.get_status_color(result['status']),
            url=result['url']
        )
        
        if result['price']:
            embed.add_field(name="Price", value=result['price'], inline=True)
        
        embed.add_field(name="Set Code", value=set_code, inline=True)
        embed.add_field(name="Status", value=result['status'].replace('_', ' ').title(), inline=True)
        
        # Show button detected if available - make it prominent and easy to read
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
            
            # Make it bigger and more visible (Discord doesn't support font size, so we use formatting)
            embed.add_field(
                name=f"{emoji} Button Detected", 
                value=f"```\n{button_text}\n```", 
                inline=False
            )
            
        # elif result.get('button_detected') is None and result['status'] != 'error':
        #     embed.add_field(
        #         name="🔘 Button Detected", 
        #         value="*None (text-based detection)*", 
        #         inline=False
        #     )
        
        if result['status'] == 'error':
            embed.add_field(name="Error Details", value=result['message'], inline=False)
                
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error in check_stock command: {e}")
        await interaction.followup.send(
            f"❌ An error occurred while checking stock for set {set_code}: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="watch", description="Add a LEGO set to your watchlist")
@app_commands.describe(set_code="The LEGO set code to watch (e.g., 10312)")
async def watch(interaction: discord.Interaction, set_code: str):
    """Add a set to the user's watchlist."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        # First verify the set exists by checking stock
        result = bot.lego_checker.check_stock(set_code)
        
        if result['status'] == 'error':
            await interaction.followup.send(
                f"❌ Could not find set {set_code}. Please verify the set code is correct.",
                ephemeral=True
            )
            return
        
        # Add to watchlist
        guild_id = interaction.guild_id if interaction.guild else None
        success = await bot.db.add_watch(interaction.user.id, set_code, guild_id)
        
        if success:
            embed = discord.Embed(
                title="✅ Added to Watchlist",
                description=f"**{result['set_name']}** (Set {set_code})",
                color=0x00ff00
            )
            embed.add_field(name="Current Status", value=result['message'], inline=False)
            embed.set_footer(text="You'll be notified when the stock status changes")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                f"⚠️ Set {set_code} is already in your watchlist.",
                ephemeral=True
            )
            
    except Exception as e:
        logger.error(f"Error in watch command: {e}")
        await interaction.followup.send(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="unwatch", description="Remove a LEGO set from your watchlist")
@app_commands.describe(set_code="The LEGO set code to unwatch (e.g., 10312)")
async def unwatch(interaction: discord.Interaction, set_code: str):
    """Remove a set from the user's watchlist."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        guild_id = interaction.guild_id if interaction.guild else None
        success = await bot.db.remove_watch(interaction.user.id, set_code, guild_id)
        
        if success:
            await interaction.followup.send(
                f"✅ Removed set {set_code} from your watchlist.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"⚠️ Set {set_code} is not in your watchlist.",
                ephemeral=True
            )
            
    except Exception as e:
        logger.error(f"Error in unwatch command: {e}")
        await interaction.followup.send(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="my-watches", description="List all sets you're watching")
async def my_watches(interaction: discord.Interaction):
    """List all sets the user is watching."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        guild_id = interaction.guild_id if interaction.guild else None
        watches = await bot.db.get_user_watches(interaction.user.id, guild_id)
        
        if not watches:
            await interaction.followup.send(
                "📋 You're not watching any sets. Use `/watch <set_code>` to add one!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title=f"📋 Your Watchlist ({len(watches)} set{'s' if len(watches) != 1 else ''})",
            color=0x0099ff
        )
        
        # Group watches into chunks if there are many
        watch_list = []
        for watch in watches[:10]:  # Limit to 10 for display
            set_code = watch['set_code']
            last_status = watch['last_status'] or 'Not checked yet'
            watch_list.append(f"**{set_code}** - {last_status.replace('_', ' ').title()}")
        
        embed.description = "\n".join(watch_list) if watch_list else "No watches found"
        
        if len(watches) > 10:
            embed.set_footer(text=f"Showing 10 of {len(watches)} sets")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in my_watches command: {e}")
        await interaction.followup.send(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="set-notification-channel", description="Set the channel where notifications will be sent (Admin only)")
@app_commands.describe(channel="The channel where notifications should be sent")
@app_commands.default_permissions(administrator=True)
async def set_notification_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Set the notification channel for the server."""
    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command can only be used in a server.",
            ephemeral=True
        )
        return
    
    # Check if user has administrator permission
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ You need administrator permissions to set the notification channel.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Check if bot can send messages in the channel
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.followup.send(
                f"❌ I don't have permission to send messages in {channel.mention}.",
                ephemeral=True
            )
            return
        
        await bot.db.set_notification_channel(interaction.guild.id, channel.id)
        await interaction.followup.send(
            f"✅ Notification channel set to {channel.mention}.\n"
            f"All stock notifications will now be sent there instead of DMs.",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error setting notification channel: {e}")
        await interaction.followup.send(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="clear-notification-channel", description="Clear the notification channel and revert to DMs (Admin only)")
@app_commands.default_permissions(administrator=True)
async def clear_notification_channel(interaction: discord.Interaction):
    """Clear the notification channel for the server."""
    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command can only be used in a server.",
            ephemeral=True
        )
        return
    
    # Check if user has administrator permission
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ You need administrator permissions to clear the notification channel.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        await bot.db.clear_notification_channel(interaction.guild.id)
        await interaction.followup.send(
            "✅ Notification channel cleared. Notifications will now be sent via DMs.",
            ephemeral=True
        )
    except Exception as e:
        logger.error(f"Error clearing notification channel: {e}")
        await interaction.followup.send(
            f"❌ An error occurred: {str(e)}",
            ephemeral=True
        )


@bot.tree.command(name="sync-commands", description="Manually sync slash commands to this server (Admin only)")
@app_commands.default_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    """Manually sync slash commands to the current guild."""
    if not interaction.guild:
        await interaction.response.send_message(
            "❌ This command can only be used in a server.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Clear any existing guild commands first to avoid duplicates
        bot.tree.clear_commands(guild=interaction.guild)
        # Copy global commands to this guild
        bot.tree.copy_global_to(guild=interaction.guild)
        # Sync to this specific guild (instant)
        synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(
            f"✅ Successfully synced {len(synced)} command(s) to this server!\n"
            f"Commands should appear immediately. Try typing `/` to see them.",
            ephemeral=True
        )
        logger.info(f"Manually synced {len(synced)} command(s) to guild {interaction.guild.name} via sync-commands")
    except Exception as e:
        logger.error(f"Error syncing commands: {e}")
        await interaction.followup.send(
            f"❌ Failed to sync commands: {str(e)}",
            ephemeral=True
        )

