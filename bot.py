"""
NWS St. Clair County Weather Alert Discord Bot
Posts severe weather warnings and updates from NWS for St. Clair County, Michigan
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import asyncio
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NWS_ZONE = "MIC147"  # St. Clair County, Michigan
NWS_OFFICE = "DTX"  # Detroit forecast office
NWS_GRID_X = 84  # Grid coordinates for Port Huron area
NWS_GRID_Y = 65
NWS_API_BASE = "https://api.weather.gov"
CHECK_INTERVAL_SECONDS = 60  # How often to check for new alerts

# Data files
POSTED_ALERTS_FILE = Path("posted_alerts.json")
SERVER_CONFIG_FILE = Path("server_config.json")

# NWS Alert severity colors for embeds
SEVERITY_COLORS = {
    "Extreme": 0xFF0000,    # Red
    "Severe": 0xFF6600,     # Orange
    "Moderate": 0xFFCC00,   # Yellow
    "Minor": 0x00CCFF,      # Light Blue
    "Unknown": 0x808080,    # Gray
}

# Alert type emojis
ALERT_EMOJIS = {
    "Tornado Warning": "\U0001F32A\uFE0F",
    "Tornado Watch": "\U0001F32A\uFE0F",
    "Severe Thunderstorm Warning": "\u26C8\uFE0F",
    "Severe Thunderstorm Watch": "\u26C8\uFE0F",
    "Flash Flood Warning": "\U0001F4A7",
    "Flash Flood Watch": "\U0001F4A7",
    "Flood Warning": "\U0001F30A",
    "Flood Watch": "\U0001F30A",
    "Winter Storm Warning": "\u2744\uFE0F",
    "Winter Storm Watch": "\u2744\uFE0F",
    "Blizzard Warning": "\U0001F328\uFE0F",
    "Ice Storm Warning": "\U0001F9CA",
    "Wind Advisory": "\U0001F4A8",
    "High Wind Warning": "\U0001F4A8",
    "Heat Advisory": "\U0001F525",
    "Excessive Heat Warning": "\U0001F525",
    "Freeze Warning": "\U0001F976",
    "Frost Advisory": "\U0001F976",
    "Dense Fog Advisory": "\U0001F32B\uFE0F",
    "Special Weather Statement": "\u2139\uFE0F",
}


class NWSAlertBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.posted_alerts = self.load_posted_alerts()
        self.server_config = self.load_server_config()
        self.session = None

    def load_posted_alerts(self) -> set:
        """Load previously posted alert IDs from file."""
        if POSTED_ALERTS_FILE.exists():
            try:
                with open(POSTED_ALERTS_FILE, "r") as f:
                    data = json.load(f)
                    # Clean old alerts (keep last 500)
                    return set(data[-500:])
            except (json.JSONDecodeError, IOError):
                return set()
        return set()

    def save_posted_alerts(self):
        """Save posted alert IDs to file."""
        with open(POSTED_ALERTS_FILE, "w") as f:
            json.dump(list(self.posted_alerts), f)

    def load_server_config(self) -> dict:
        """Load server configuration from file."""
        if SERVER_CONFIG_FILE.exists():
            try:
                with open(SERVER_CONFIG_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def save_server_config(self):
        """Save server configuration to file."""
        with open(SERVER_CONFIG_FILE, "w") as f:
            json.dump(self.server_config, f, indent=2)

    def set_alert_channel(self, guild_id: int, channel_id: int):
        """Set the alert channel for a server."""
        self.server_config[str(guild_id)] = {"alert_channel_id": channel_id}
        self.save_server_config()

    def remove_alert_channel(self, guild_id: int):
        """Remove the alert channel configuration for a server."""
        guild_key = str(guild_id)
        if guild_key in self.server_config:
            del self.server_config[guild_key]
            self.save_server_config()
            return True
        return False

    def get_alert_channel(self, guild_id: int) -> int | None:
        """Get the alert channel ID for a server."""
        guild_key = str(guild_id)
        if guild_key in self.server_config:
            return self.server_config[guild_key].get("alert_channel_id")
        return None

    def get_all_alert_channels(self) -> list[int]:
        """Get all configured alert channel IDs."""
        channels = []
        for guild_config in self.server_config.values():
            channel_id = guild_config.get("alert_channel_id")
            if channel_id:
                channels.append(channel_id)
        return channels

    async def setup_hook(self):
        """Called when the bot is starting up."""
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": "(NWSStClairBot, Discord Weather Alert Bot)"}
        )
        self.check_alerts.start()
        # Sync slash commands globally
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s) globally")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    async def close(self):
        """Cleanup when bot shuts down."""
        self.check_alerts.cancel()
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self):
        print(f"Bot is ready! Logged in as {self.user}")
        print(f"Monitoring NWS alerts for zone: {NWS_ZONE}")
        print(f"Connected to {len(self.guilds)} server(s)")
        print(f"Alert channels configured: {len(self.server_config)}")
        for guild in self.guilds:
            print(f"  - {guild.name} (ID: {guild.id})")

    async def fetch_alerts(self) -> list:
        """Fetch current alerts from NWS API for our zone."""
        url = f"{NWS_API_BASE}/alerts/active/zone/{NWS_ZONE}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("features", [])
                else:
                    print(f"NWS API returned status {response.status}")
                    return []
        except Exception as e:
            print(f"Error fetching alerts: {e}")
            return []

    async def fetch_forecast(self) -> list:
        """Fetch the 7-day forecast from NWS API."""
        url = f"{NWS_API_BASE}/gridpoints/{NWS_OFFICE}/{NWS_GRID_X},{NWS_GRID_Y}/forecast"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("properties", {}).get("periods", [])
                else:
                    print(f"NWS Forecast API returned status {response.status}")
                    return []
        except Exception as e:
            print(f"Error fetching forecast: {e}")
            return []

    async def fetch_hourly_forecast(self) -> list:
        """Fetch the hourly forecast from NWS API."""
        url = f"{NWS_API_BASE}/gridpoints/{NWS_OFFICE}/{NWS_GRID_X},{NWS_GRID_Y}/forecast/hourly"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("properties", {}).get("periods", [])
                else:
                    print(f"NWS Hourly Forecast API returned status {response.status}")
                    return []
        except Exception as e:
            print(f"Error fetching hourly forecast: {e}")
            return []

    async def fetch_discussion(self) -> dict:
        """Fetch the Area Forecast Discussion from NWS API."""
        url = f"{NWS_API_BASE}/products/types/AFD/locations/{NWS_OFFICE}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    products = data.get("@graph", [])
                    if products:
                        # Get the latest discussion
                        latest_url = products[0].get("@id", "")
                        if latest_url:
                            async with self.session.get(latest_url) as prod_response:
                                if prod_response.status == 200:
                                    prod_data = await prod_response.json()
                                    return prod_data
                return {}
        except Exception as e:
            print(f"Error fetching discussion: {e}")
            return {}

    async def fetch_hazardous_outlook(self) -> dict:
        """Fetch the Hazardous Weather Outlook from NWS API."""
        url = f"{NWS_API_BASE}/products/types/HWO/locations/{NWS_OFFICE}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    products = data.get("@graph", [])
                    if products:
                        # Get the latest outlook
                        latest_url = products[0].get("@id", "")
                        if latest_url:
                            async with self.session.get(latest_url) as prod_response:
                                if prod_response.status == 200:
                                    prod_data = await prod_response.json()
                                    return prod_data
                return {}
        except Exception as e:
            print(f"Error fetching hazardous outlook: {e}")
            return {}

    def create_alert_embed(self, alert: dict) -> discord.Embed:
        """Create a Discord embed for an alert."""
        props = alert.get("properties", {})

        event = props.get("event", "Unknown Alert")
        severity = props.get("severity", "Unknown")
        headline = props.get("headline", "No headline available")
        description = props.get("description", "No description available")
        instruction = props.get("instruction", "")

        # Parse times
        effective = props.get("effective", "")
        expires = props.get("expires", "")

        # Get emoji for alert type
        emoji = ALERT_EMOJIS.get(event, "\u26A0\uFE0F")

        # Get color based on severity
        color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["Unknown"])

        # Create embed
        embed = discord.Embed(
            title=f"{emoji} {event}",
            description=headline,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )

        # Truncate description if too long (Discord limit is 4096 for embed description)
        if len(description) > 1024:
            description = description[:1021] + "..."
        embed.add_field(name="Description", value=description, inline=False)

        if instruction:
            if len(instruction) > 1024:
                instruction = instruction[:1021] + "..."
            embed.add_field(name="Instructions", value=instruction, inline=False)

        # Format times
        if effective:
            try:
                eff_dt = datetime.fromisoformat(effective.replace("Z", "+00:00"))
                embed.add_field(
                    name="Effective",
                    value=f"<t:{int(eff_dt.timestamp())}:F>",
                    inline=True
                )
            except ValueError:
                embed.add_field(name="Effective", value=effective, inline=True)

        if expires:
            try:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                embed.add_field(
                    name="Expires",
                    value=f"<t:{int(exp_dt.timestamp())}:F>",
                    inline=True
                )
            except ValueError:
                embed.add_field(name="Expires", value=expires, inline=True)

        embed.add_field(name="Severity", value=severity, inline=True)

        # Add NWS attribution
        embed.set_footer(text="Source: National Weather Service")

        return embed

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def check_alerts(self):
        """Periodically check for new alerts and post them to all configured channels."""
        # Get all configured alert channels
        alert_channels = self.get_all_alert_channels()

        if not alert_channels:
            return  # No channels configured yet

        alerts = await self.fetch_alerts()

        for alert in alerts:
            alert_id = alert.get("properties", {}).get("id", "")

            if alert_id and alert_id not in self.posted_alerts:
                # New alert - post it to all configured channels!
                embed = self.create_alert_embed(alert)

                # Determine if we should ping @everyone for severe alerts
                severity = alert.get("properties", {}).get("severity", "")
                event = alert.get("properties", {}).get("event", "")

                # Ping for tornado warnings and other extreme events
                ping_events = ["Tornado Warning", "Flash Flood Warning", "Blizzard Warning"]
                content = ""
                if severity == "Extreme" or event in ping_events:
                    content = "@everyone **SEVERE WEATHER ALERT**"

                # Post to all configured channels
                posted_successfully = False
                for channel_id in alert_channels:
                    channel = self.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.send(content=content, embed=embed)
                            posted_successfully = True
                            print(f"Posted alert to {channel.guild.name}: {event}")
                        except discord.DiscordException as e:
                            print(f"Error posting alert to channel {channel_id}: {e}")
                    else:
                        print(f"Could not find channel with ID {channel_id}")

                # Only mark as posted if at least one channel received it
                if posted_successfully:
                    self.posted_alerts.add(alert_id)
                    self.save_posted_alerts()
                    print(f"Alert tracked: {alert_id}")

    @check_alerts.before_loop
    async def before_check_alerts(self):
        """Wait until the bot is ready before starting the alert check loop."""
        await self.wait_until_ready()


# Bot instance
bot = NWSAlertBot()


# Global error handler for slash commands
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handle errors in slash commands."""
    print(f"Command error: {error}")
    if interaction.response.is_done():
        await interaction.followup.send(f"An error occurred: {error}", ephemeral=True)
    else:
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)


# Weather condition emojis for forecast
WEATHER_EMOJIS = {
    "sunny": "\u2600\uFE0F",
    "clear": "\u2600\uFE0F",
    "mostly sunny": "\U0001F324\uFE0F",
    "mostly clear": "\U0001F324\uFE0F",
    "partly sunny": "\u26C5",
    "partly cloudy": "\u26C5",
    "mostly cloudy": "\U0001F325\uFE0F",
    "cloudy": "\u2601\uFE0F",
    "overcast": "\u2601\uFE0F",
    "rain": "\U0001F327\uFE0F",
    "showers": "\U0001F327\uFE0F",
    "thunderstorm": "\u26C8\uFE0F",
    "snow": "\U0001F328\uFE0F",
    "sleet": "\U0001F328\uFE0F",
    "freezing": "\U0001F9CA",
    "fog": "\U0001F32B\uFE0F",
    "windy": "\U0001F4A8",
    "hot": "\U0001F525",
    "cold": "\U0001F976",
}


def get_weather_emoji(forecast_text: str) -> str:
    """Get an appropriate emoji for the weather condition."""
    text_lower = forecast_text.lower()
    for keyword, emoji in WEATHER_EMOJIS.items():
        if keyword in text_lower:
            return emoji
    return "\U0001F324\uFE0F"  # Default


# Slash Commands
@bot.tree.command(name="alerts", description="Show current active weather alerts for St. Clair County")
async def slash_alerts(interaction: discord.Interaction):
    """Display current active alerts for St. Clair County."""
    await interaction.response.defer()

    alerts = await bot.fetch_alerts()

    if not alerts:
        await interaction.followup.send("No active weather alerts for St. Clair County at this time.")
        return

    await interaction.followup.send(f"**{len(alerts)} Active Alert(s) for St. Clair County:**")
    for alert in alerts[:5]:  # Limit to 5 to avoid spam
        embed = bot.create_alert_embed(alert)
        await interaction.channel.send(embed=embed)


@bot.tree.command(name="forecast", description="Get the weather forecast for St. Clair County")
@app_commands.describe(days="Number of forecast periods to show (default: 6, max: 14)")
async def slash_forecast(interaction: discord.Interaction, days: int = 6):
    """Display the weather forecast for St. Clair County."""
    await interaction.response.defer()

    periods = await bot.fetch_forecast()

    if not periods:
        await interaction.followup.send("Unable to fetch forecast. Please try again later.")
        return

    # Limit days
    days = min(max(days, 1), 14)
    periods = periods[:days]

    embed = discord.Embed(
        title=f"\U0001F324\uFE0F Weather Forecast - St. Clair County, MI",
        color=0x3498DB,
        timestamp=datetime.now(timezone.utc)
    )

    for period in periods:
        name = period.get("name", "Unknown")
        temp = period.get("temperature", "?")
        temp_unit = period.get("temperatureUnit", "F")
        short_forecast = period.get("shortForecast", "No forecast available")
        wind_speed = period.get("windSpeed", "Unknown")
        wind_dir = period.get("windDirection", "")

        emoji = get_weather_emoji(short_forecast)

        value = f"{emoji} **{temp}\u00B0{temp_unit}** - {short_forecast}\n"
        value += f"\U0001F4A8 Wind: {wind_speed} {wind_dir}"

        embed.add_field(name=name, value=value, inline=False)

    embed.set_footer(text="Source: National Weather Service")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="hourly", description="Get the hourly forecast for St. Clair County")
@app_commands.describe(hours="Number of hours to show (default: 12, max: 24)")
async def slash_hourly(interaction: discord.Interaction, hours: int = 12):
    """Display the hourly forecast for St. Clair County."""
    await interaction.response.defer()

    periods = await bot.fetch_hourly_forecast()

    if not periods:
        await interaction.followup.send("Unable to fetch hourly forecast. Please try again later.")
        return

    # Limit hours
    hours = min(max(hours, 1), 24)
    periods = periods[:hours]

    embed = discord.Embed(
        title=f"\u23F0 Hourly Forecast - St. Clair County, MI",
        color=0x9B59B6,
        timestamp=datetime.now(timezone.utc)
    )

    forecast_text = ""
    for period in periods:
        start_time = period.get("startTime", "")
        temp = period.get("temperature", "?")
        short_forecast = period.get("shortForecast", "")

        # Parse and format time
        try:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            time_str = f"<t:{int(dt.timestamp())}:t>"
        except (ValueError, AttributeError):
            time_str = "Unknown"

        emoji = get_weather_emoji(short_forecast)
        forecast_text += f"{time_str}: {emoji} **{temp}\u00B0F** - {short_forecast}\n"

    # Split into chunks if too long
    if len(forecast_text) > 4096:
        forecast_text = forecast_text[:4093] + "..."

    embed.description = forecast_text
    embed.set_footer(text="Source: National Weather Service")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="outlook", description="Get the Hazardous Weather Outlook for the region")
async def slash_outlook(interaction: discord.Interaction):
    """Display the Hazardous Weather Outlook."""
    await interaction.response.defer()

    outlook = await bot.fetch_hazardous_outlook()

    if not outlook:
        await interaction.followup.send("Unable to fetch hazardous weather outlook. Please try again later.")
        return

    product_text = outlook.get("productText", "No outlook text available")
    issue_time = outlook.get("issuanceTime", "")

    # Parse issue time
    time_str = ""
    if issue_time:
        try:
            dt = datetime.fromisoformat(issue_time.replace("Z", "+00:00"))
            time_str = f"Issued: <t:{int(dt.timestamp())}:F>"
        except ValueError:
            time_str = f"Issued: {issue_time}"

    embed = discord.Embed(
        title="\u26A0\uFE0F Hazardous Weather Outlook",
        color=0xE74C3C,
        timestamp=datetime.now(timezone.utc)
    )

    if time_str:
        embed.description = time_str

    # Truncate if too long and split into fields
    if len(product_text) > 4000:
        product_text = product_text[:4000] + "..."

    # Split into chunks of 1024 for fields
    chunks = [product_text[i:i+1024] for i in range(0, len(product_text), 1024)]
    for i, chunk in enumerate(chunks[:4]):  # Max 4 fields
        field_name = "Outlook" if i == 0 else "\u200b"  # Invisible character for continuation
        embed.add_field(name=field_name, value=chunk, inline=False)

    embed.set_footer(text=f"Source: NWS {NWS_OFFICE}")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="discussion", description="Get the Area Forecast Discussion from NWS")
async def slash_discussion(interaction: discord.Interaction):
    """Display the Area Forecast Discussion (technical meteorological analysis)."""
    await interaction.response.defer()

    discussion = await bot.fetch_discussion()

    if not discussion:
        await interaction.followup.send("Unable to fetch forecast discussion. Please try again later.")
        return

    product_text = discussion.get("productText", "No discussion text available")
    issue_time = discussion.get("issuanceTime", "")

    # Parse issue time
    time_str = ""
    if issue_time:
        try:
            dt = datetime.fromisoformat(issue_time.replace("Z", "+00:00"))
            time_str = f"Issued: <t:{int(dt.timestamp())}:F>"
        except ValueError:
            time_str = f"Issued: {issue_time}"

    embed = discord.Embed(
        title="\U0001F4DD Area Forecast Discussion",
        description=time_str if time_str else None,
        color=0x2ECC71,
        timestamp=datetime.now(timezone.utc)
    )

    # AFDs are long - extract key sections or truncate
    # Try to extract the synopsis section
    lines = product_text.split("\n")
    synopsis = []
    in_synopsis = False

    for line in lines:
        if ".SYNOPSIS" in line.upper() or "SYNOPSIS" in line.upper():
            in_synopsis = True
            continue
        elif line.startswith(".") and in_synopsis:
            break
        elif in_synopsis:
            synopsis.append(line)

    synopsis_text = "\n".join(synopsis).strip()[:1024] if synopsis else product_text[:1024]

    if synopsis_text:
        embed.add_field(name="Synopsis", value=synopsis_text or "See full discussion", inline=False)

    # Add note about full discussion
    embed.add_field(
        name="Full Discussion",
        value=f"[View on NWS Website](https://forecast.weather.gov/product.php?site={NWS_OFFICE}&issuedby={NWS_OFFICE}&product=AFD)",
        inline=False
    )

    embed.set_footer(text=f"Source: NWS {NWS_OFFICE}")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="status", description="Show bot status and monitoring information")
async def slash_status(interaction: discord.Interaction):
    """Show bot status and monitoring info."""
    embed = discord.Embed(
        title="NWS Alert Bot Status",
        color=0x00FF00,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Monitoring Zone", value=f"{NWS_ZONE} (St. Clair County, MI)", inline=False)
    embed.add_field(name="Forecast Office", value=NWS_OFFICE, inline=True)
    embed.add_field(name="Check Interval", value=f"Every {CHECK_INTERVAL_SECONDS} seconds", inline=True)
    embed.add_field(name="Servers Connected", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Channels Configured", value=str(len(bot.server_config)), inline=True)
    embed.add_field(name="Alerts Tracked", value=str(len(bot.posted_alerts)), inline=True)
    embed.add_field(name="Bot Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="test", description="Send a test alert embed (Manage Server required)")
@app_commands.guild_only()
async def slash_test(interaction: discord.Interaction):
    """Send a test alert embed (Manage Server required)."""
    # Check for Manage Server permission
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You need Manage Server permission to use this command.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title="\u26A0\uFE0F Test Alert",
        description="This is a test alert to verify the bot is working correctly.",
        color=0x00FF00,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Description", value="If you can see this message, the bot is configured correctly and can post alerts to this channel.", inline=False)
    embed.add_field(name="Zone", value=f"{NWS_ZONE} (St. Clair County, MI)", inline=True)
    embed.set_footer(text="Source: Test - National Weather Service Bot")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="setchannel", description="Set the channel for weather alerts (Manage Server required)")
@app_commands.describe(channel="The channel where weather alerts will be posted")
@app_commands.guild_only()
async def slash_setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    """Set the alert channel for this server."""
    try:
        # Check for Manage Server permission
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need Manage Server permission to use this command.", ephemeral=True
            )
            return

        bot.set_alert_channel(interaction.guild.id, channel.id)

        embed = discord.Embed(
            title="\u2705 Alert Channel Configured",
            description=f"Weather alerts will now be posted to {channel.mention}",
            color=0x00FF00,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Zone", value=f"{NWS_ZONE} (St. Clair County, MI)", inline=True)
        embed.add_field(name="Check Interval", value=f"Every {CHECK_INTERVAL_SECONDS} seconds", inline=True)
        embed.set_footer(text="Use /removechannel to stop receiving alerts")
        await interaction.response.send_message(embed=embed)
        print(f"Alert channel set for {interaction.guild.name}: #{channel.name}")
    except Exception as e:
        print(f"Error in setchannel command: {e}")
        await interaction.response.send_message(f"Error setting channel: {e}", ephemeral=True)


@bot.tree.command(name="removechannel", description="Stop receiving weather alerts in this server (Manage Server required)")
@app_commands.guild_only()
async def slash_removechannel(interaction: discord.Interaction):
    """Remove the alert channel configuration for this server."""
    # Check for Manage Server permission
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You need Manage Server permission to use this command.", ephemeral=True
        )
        return

    if bot.remove_alert_channel(interaction.guild.id):
        embed = discord.Embed(
            title="\u274C Alerts Disabled",
            description="This server will no longer receive weather alerts.",
            color=0xFF0000,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="Use /setchannel to re-enable alerts")
        await interaction.response.send_message(embed=embed)
        print(f"Alert channel removed for {interaction.guild.name}")
    else:
        await interaction.response.send_message("No alert channel was configured for this server.", ephemeral=True)


@bot.tree.command(name="channelinfo", description="Show the current alert channel configuration")
async def slash_channelinfo(interaction: discord.Interaction):
    """Show the current alert channel for this server."""
    if not interaction.guild:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    channel_id = bot.get_alert_channel(interaction.guild.id)

    if channel_id:
        channel = interaction.guild.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title="\U0001F4E2 Alert Channel Configuration",
                description=f"Weather alerts are being sent to {channel.mention}",
                color=0x3498DB,
                timestamp=datetime.now(timezone.utc)
            )
        else:
            embed = discord.Embed(
                title="\u26A0\uFE0F Channel Not Found",
                description=f"Configured channel (ID: {channel_id}) no longer exists.\nUse `/setchannel` to set a new channel.",
                color=0xFFCC00,
                timestamp=datetime.now(timezone.utc)
            )
    else:
        embed = discord.Embed(
            title="\U0001F4E2 No Channel Configured",
            description="No alert channel has been set for this server.\nUse `/setchannel #channel` to configure alerts.",
            color=0x808080,
            timestamp=datetime.now(timezone.utc)
        )

    embed.set_footer(text=f"Zone: {NWS_ZONE} | Office: {NWS_OFFICE}")
    await interaction.response.send_message(embed=embed)


def main():
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set!")
        print("Please create a .env file with your bot token.")
        return

    print("Starting NWS St. Clair County Alert Bot...")
    print("Use /setchannel in your server to configure alert channels.")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
