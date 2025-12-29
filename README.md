# NWS St. Clair County Weather Alert Bot

Discord bot that posts severe weather warnings and updates from the National Weather Service for St. Clair County, Michigan.

## Features

- **Multi-server support** - One bot instance can serve multiple Discord servers
- Automatically polls NWS API every 60 seconds for new alerts
- Posts formatted embeds with color-coded severity levels
- Pings @everyone for extreme/tornado warnings
- Tracks posted alerts to prevent duplicates
- Slash commands for forecast, outlook, hourly conditions, and more
- Weather condition emojis for easy visual identification
- Per-server channel configuration via `/setchannel`

## Setup

### 1. Get Your Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application (ID: `1455220788767625381`)
3. Go to **Bot** section in the left sidebar
4. Click **Reset Token** and copy the token

### 2. Enable Required Intents

In the Discord Developer Portal under **Bot**:
- Enable **Message Content Intent** (required for commands)

### 3. Invite Bot to Server

1. Go to **OAuth2 > URL Generator**
2. Select scopes: `bot` and `applications.commands`
3. Select permissions:
   - Send Messages
   - Embed Links
   - Mention Everyone (for severe alerts)
   - Read Message History
4. Copy the generated URL and open it to invite the bot

### 4. Configure the Bot

1. Copy `.env.example` to `.env`:
   ```
   copy .env.example .env
   ```

2. Edit `.env` with your bot token:
   - `DISCORD_TOKEN`: Your bot token from step 1

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Run the Bot

```bash
python bot.py
```

### 7. Configure Alert Channel (In Discord)

Once the bot is running and invited to your server:
1. Use `/setchannel #your-weather-channel` to set where alerts will be posted
2. The bot will confirm the configuration
3. Alerts will now be automatically posted to that channel

## Slash Commands

### Weather Commands

| Command | Description |
|---------|-------------|
| `/alerts` | Show current active weather alerts for St. Clair County |
| `/forecast [days]` | Get the 7-day weather forecast (default: 6 periods) |
| `/hourly [hours]` | Get the hourly forecast (default: 12 hours, max: 24) |
| `/outlook` | Get the Hazardous Weather Outlook from NWS |
| `/discussion` | Get the Area Forecast Discussion (technical analysis) |
| `/status` | Display bot status and monitoring info |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/setchannel #channel` | Set the channel for weather alerts (Admin only) |
| `/removechannel` | Stop receiving alerts in this server (Admin only) |
| `/channelinfo` | Show current alert channel configuration |
| `/test` | Send a test alert embed (Admin only) |

**Note:** Slash commands sync automatically when the bot starts. It may take a few minutes for them to appear in Discord after the first run.

## Alert Types & Colors

- **Red** - Extreme (Tornado Warning, etc.)
- **Orange** - Severe (Severe Thunderstorm Warning, etc.)
- **Yellow** - Moderate
- **Light Blue** - Minor
- **Gray** - Unknown

## Running as a Service

For 24/7 operation, consider running the bot as a Windows service or using a process manager.

### Using NSSM (Windows)

1. Download [NSSM](https://nssm.cc/)
2. Run: `nssm install NWSAlertBot`
3. Set path to your Python executable and bot.py

### Using systemd (Linux)

Create `/etc/systemd/system/nws-alert-bot.service`:

```ini
[Unit]
Description=NWS Alert Discord Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/NWSStClairBot
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Configuration

Edit `bot.py` to customize:

- `CHECK_INTERVAL_SECONDS`: How often to check for alerts (default: 60)
- `NWS_ZONE`: NWS zone code (MIC147 for St. Clair County)
- `NWS_OFFICE`: NWS forecast office (DTX for Detroit)
- `NWS_GRID_X` / `NWS_GRID_Y`: Grid coordinates for forecast location
- `ping_events`: List of events that trigger @everyone mentions

## Data Files

The bot creates these files automatically:

- `server_config.json` - Stores per-server alert channel configurations
- `posted_alerts.json` - Tracks which alerts have been posted (prevents duplicates)

## License

MIT
