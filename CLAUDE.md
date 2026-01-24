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
- Message ID tracking for cleanup (`message_tracking.json`) - persists across restarts

### Alert Processing Flow

1. `check_alerts()` task loop runs every 60 seconds
2. Fetches active alerts from NWS API for zone `MIC147` (St. Clair County)
3. If API returns error (non-200 or exception), skips cycle entirely to prevent false all-clear
4. Compares current alerts with `active_alert_ids` from previous check
5. If alerts were active but now cleared:
   - Deletes all previous alert messages (tracked in `alert_message_ids`)
   - Posts all-clear notification via `post_all_clear()`
   - Tracks all-clear message ID in `all_clear_message_ids`
6. For each new alert:
   - Deletes any existing all-clear messages first
   - Creates formatted Discord embed via `create_alert_embed()`
   - Determines if @everyone ping needed (Extreme severity or specific events)
   - Posts to all configured guild channels
   - Tracks message ID in `alert_message_ids` for later deletion
   - Tracks alert ID to prevent re-posting

### API Error Handling

`fetch_alerts()` returns `None` on API errors instead of an empty list. This prevents the bot from incorrectly interpreting an API failure as "no active alerts" and triggering a false all-clear that would delete valid alert messages.

### API Endpoints Used

All fetch methods hit `api.weather.gov`:
- `/alerts/active/zone/{zone}` - Active weather alerts
- `/gridpoints/{office}/{x},{y}/forecast` - 7-day forecast
- `/gridpoints/{office}/{x},{y}/forecast/hourly` - Hourly forecast
- `/products/types/AFD/locations/{office}` - Area Forecast Discussion
- `/products/types/HWO/locations/{office}` - Hazardous Weather Outlook

### Radar Images

Radar GIFs are fetched from `radar.weather.gov/ridge/standard/KDTX_loop.gif` and attached directly to Discord messages rather than embedded via URL. This bypasses Discord's external image proxy which can be unreliable. The `fetch_radar_image()` method downloads the GIF bytes, and messages use `attachment://radar.gif` to reference the attached file.

### Slash Commands

10 commands registered - weather info (`/alerts`, `/forecast`, `/hourly`, `/outlook`, `/discussion`, `/status`) and server management (`/setchannel`, `/removechannel`, `/channelinfo`, `/test`, `/sync`, `/reset`).

Management commands require `manage_guild` permission.

`/reset` clears all tracking data (posted alerts, message IDs, active alert state) and triggers an immediate alert recheck, causing current alerts to be reposted.

Bot requires "Manage Messages" permission in alert channels to delete old alerts when all-clear is posted.

### Configuration Constants

Hardcoded in `bot.py`:
- `NWS_ZONE = "MIC147"` - St. Clair County zone
- `NWS_OFFICE = "DTX"` - Detroit forecast office
- `NWS_GRID_X/Y = (84, 65)` - Port Huron grid coordinates
- `CHECK_INTERVAL_SECONDS = 60`

### Runtime Files

- `server_config.json` - Guild ID → Channel ID mapping
- `posted_alerts.json` - List of posted alert IDs
- `message_tracking.json` - Tracks alert and all-clear message IDs for deletion (persists across restarts)

## Environment

Requires `.env` file with `DISCORD_TOKEN`. Copy from `.env.example`.
