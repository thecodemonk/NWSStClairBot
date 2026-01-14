# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Discord bot that monitors the National Weather Service API and posts severe weather alerts to Discord servers. Built with Python and discord.py.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python bot.py
```

No tests or linting configured.

## Architecture

**Single-file bot (`bot.py`)** with async/await throughout using `aiohttp` for HTTP and discord.py task loops.

### Core Class: `NWSAlertBot`

Main bot class that handles:
- Discord connection lifecycle
- HTTP session management for NWS API calls
- Per-server channel configuration (`server_config.json`)
- Posted alert tracking to prevent duplicates (`posted_alerts.json`, capped at 500)

### Alert Processing Flow

1. `check_alerts()` task loop runs every 60 seconds
2. Fetches active alerts from NWS API for zone `MIC147` (St. Clair County)
3. For each new alert:
   - Creates formatted Discord embed via `create_alert_embed()`
   - Determines if @everyone ping needed (Extreme severity or specific events)
   - Posts to all configured guild channels
   - Tracks alert ID to prevent re-posting

### API Endpoints Used

All fetch methods hit `api.weather.gov`:
- `/alerts/active/zone/{zone}` - Active weather alerts
- `/gridpoints/{office}/{x},{y}/forecast` - 7-day forecast
- `/gridpoints/{office}/{x},{y}/forecast/hourly` - Hourly forecast
- `/products/types/AFD/locations/{office}` - Area Forecast Discussion
- `/products/types/HWO/locations/{office}` - Hazardous Weather Outlook

### Slash Commands

9 commands registered - weather info (`/alerts`, `/forecast`, `/hourly`, `/outlook`, `/discussion`, `/status`) and server management (`/setchannel`, `/removechannel`, `/channelinfo`, `/test`, `/sync`).

Management commands require `manage_guild` permission. `/sync` is restricted to server owner.

### Configuration Constants

Hardcoded in `bot.py`:
- `NWS_ZONE = "MIC147"` - St. Clair County zone
- `NWS_OFFICE = "DTX"` - Detroit forecast office
- `NWS_GRID_X/Y = (84, 65)` - Port Huron grid coordinates
- `CHECK_INTERVAL_SECONDS = 60`

### Runtime Files

- `server_config.json` - Guild ID → Channel ID mapping
- `posted_alerts.json` - List of posted alert IDs

## Environment

Requires `.env` file with `DISCORD_TOKEN`. Copy from `.env.example`.
