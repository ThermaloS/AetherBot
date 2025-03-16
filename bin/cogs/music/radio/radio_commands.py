import discord
import logging
from discord.ext import commands
from discord import app_commands
from typing import Optional

from bin.cogs.music.radio.radio_core import RadioCore

logger = logging.getLogger('discord_bot.radio.commands')

class RadioCommands(commands.Cog, name="Radio"):
    """Commands for controlling radio-like music playback (autoplay)."""
    
    def __init__(self, bot: commands.Bot, radio_core: RadioCore):
        """
        Initialize the radio commands.
        
        Args:
            bot: The bot instance
            radio_core: The RadioCore instance for radio functionality
        """
        self.bot = bot
        self.radio_core = radio_core
        super().__init__()
        logger.info("RadioCommands initialized")

    @app_commands.command(name="radio", description="Toggle radio mode on/off")
    @app_commands.describe(state="Turn radio mode on or off")
    @app_commands.choices(state=[
        app_commands.Choice(name="On", value="on"),
        app_commands.Choice(name="Off", value="off")
    ])
    async def radio_toggle(self, interaction: discord.Interaction, state: str):
        """
        Toggle radio mode on or off.
        
        Args:
            interaction: Discord interaction
            state: "on" or "off"
        """
        guild_id = interaction.guild_id
        
        if state == "on":
            self.radio_core.radio_enabled[guild_id] = True
            
            embed = discord.Embed(
                title="Radio Mode Enabled",
                description="🎶 Radio mode is now **ON**",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="How It Works",
                value="When the queue gets low, I'll automatically add similar songs based on what's playing.",
                inline=False
            )
        else:
            self.radio_core.radio_enabled[guild_id] = False
            embed = discord.Embed(
                title="Radio Mode Disabled",
                description="🎶 Radio mode is now **OFF**",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="Queue Behavior",
                value="The bot will now stop playing when the queue is empty.",
                inline=False
            )
        
        # Save configuration
        self.radio_core.save_config()
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="radio_status", description="Show current radio status")
    async def radio_status_command(self, interaction: discord.Interaction):
        """
        Show the current radio status.
        
        Args:
            interaction: Discord interaction
        """
        guild_id = interaction.guild_id
        
        # Check if radio is enabled
        is_enabled = self.radio_core.radio_enabled.get(guild_id, False)
        
        if not is_enabled:
            embed = discord.Embed(
                title="Radio Status",
                description="🎶 Radio mode is **OFF**",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Turn On Radio",
                value="Use `/radio on` to enable radio mode",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="Radio Status",
                description="🎶 Radio mode is **ON**",
                color=discord.Color.green()
            )
            
            # Show queue info
            queue = self.radio_core.music_cog.song_queues.get(str(guild_id), [])
            if queue:
                embed.add_field(
                    name="Queue",
                    value=f"{len(queue)} songs in queue",
                    inline=True
                )
            
            # Show recently played songs if available
            if guild_id in self.radio_core.recently_played and self.radio_core.recently_played[guild_id]:
                recent_titles = [rt for _, rt in self.radio_core.recently_played[guild_id]]
                recent_str = "\n".join([f"• {title}" for title in recent_titles[-3:]])  # Show last 3
                embed.add_field(
                    name="Recently Played",
                    value=recent_str,
                    inline=False
                )
            
            embed.add_field(
                name="How It Works",
                value="When the queue gets low, I'll automatically add similar songs based on what's playing.",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot, radio_core: Optional[RadioCore] = None):
    """
    Setup function to register the cog with the bot.
    
    Args:
        bot: The Discord bot instance
        radio_core: The RadioCore instance
    """
    if radio_core is None:
        # Try to get the radio core if it wasn't passed
        radio_core = bot.get_cog("RadioCore")
        if radio_core is None:
            logger.error("RadioCore not found. Cannot load RadioCommands.")
            return None
            
    cog = RadioCommands(bot, radio_core)
    await bot.add_cog(cog)
    logger.info("Radio Commands loaded")
    return cog