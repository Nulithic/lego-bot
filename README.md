# LEGO Stock Checker Discord Bot

A Discord bot that monitors LEGO.com for set availability, allowing users to check stock manually via commands and set up automatic monitoring for specific sets.

## Features

- **Manual Stock Checks**: Use `/check-stock <set_code>` to check if a LEGO set is in stock
- **Watchlist Monitoring**: Add sets to your watchlist with `/watch <set_code>` and get notified when they come in stock
- **Persistent Storage**: Your watchlist is saved in a database and persists across bot restarts
- **Automatic Notifications**: The bot periodically checks watched sets and sends notifications when stock status changes

## Setup

### Prerequisites

- Python 3.8 or higher
- A Discord bot token (get one from [Discord Developer Portal](https://discord.com/developers/applications))

### Installation

1. Clone or download this repository
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root:

   ```
   DISCORD_BOT_TOKEN=your_bot_token_here
   MONITOR_INTERVAL_MINUTES=5
   RATE_LIMIT_DELAY_SECONDS=2
   ```

4. Run the bot:
   ```bash
   python main.py
   ```

### Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section and create a bot
4. Copy the bot token and add it to your `.env` file
5. Enable the following bot intents:
   - Message Content Intent
   - Server Members Intent (if needed)
6. Invite the bot to your server with the following permissions:
   - Send Messages
   - Use Slash Commands
   - Embed Links
   - View Channels (to access notification channels)

## Usage

### Commands

- `/check-stock <set_code>` - Check the current stock status of a LEGO set

  - Example: `/check-stock 10312` (checks the Jazz Club set)

- `/watch <set_code>` - Add a set to your watchlist

  - Example: `/watch 10312`

- `/unwatch <set_code>` - Remove a set from your watchlist

  - Example: `/unwatch 10312`

- `/my-watches` - List all sets you're currently watching

  - Example: `/my-watches`

- `/set-notification-channel <channel>` - Set a channel where all notifications will be sent (Admin only)

  - Example: `/set-notification-channel #lego-notifications`
  - Requires administrator permissions
  - When set, all stock and button notifications will be sent to this channel instead of DMs
  - Users will still be mentioned in the channel

- `/clear-notification-channel` - Clear the notification channel and revert to DMs (Admin only)

  - Example: `/clear-notification-channel`
  - Requires administrator permissions
  - After clearing, notifications will be sent via DMs again

### How It Works

1. The bot scrapes LEGO.com product pages to check stock availability
2. When you add a set to your watchlist, the bot stores it in a database
3. A background task periodically checks all watched sets (default: every 5 minutes)
4. When a set's stock status changes (e.g., out of stock → in stock), you'll receive a notification

## Configuration

You can customize the bot behavior by editing your `.env` file:

- `MONITOR_INTERVAL_MINUTES`: How often to check watched sets (default: 5)
- `RATE_LIMIT_DELAY_SECONDS`: Delay between requests to LEGO.com (default: 2)

## Notes

- Set codes are typically 4-5 digit numbers (e.g., 10312, 75192)
- The bot respects rate limits to avoid overwhelming LEGO.com's servers
- Stock status is determined by parsing the LEGO.com product page HTML

## Testing

### Test Stock Checking
Run the test script to verify stock checking functionality:
```bash
python test_stock_check.py
```

### Test Notifications
To test notification functionality:
```bash
python test_notification.py
```
This will prompt you for:
- Your Discord User ID (right-click your profile in Discord > Copy ID)
- Optional: Guild/Server ID
- A LEGO set code to test with

The script will send test notifications to verify the notification system works.

## Troubleshooting

- **Bot doesn't respond**: Make sure the bot token is correct and the bot is invited to your server
- **Commands not showing**: Make sure the bot has the "Use Slash Commands" permission
- **403 Forbidden errors**: LEGO.com may be blocking automated requests. This can happen if:
  - You're making too many requests too quickly (increase `RATE_LIMIT_DELAY_SECONDS` in `.env`)
  - LEGO.com has updated their bot protection
  - Your IP address has been temporarily blocked
  - **Solution**: Wait a few minutes and try again, or increase the rate limit delay
- **Stock checks fail**: LEGO.com may have changed their page structure, or there may be network issues
