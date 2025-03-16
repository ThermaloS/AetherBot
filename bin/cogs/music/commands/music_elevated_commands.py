import random
import discord
from discord.ext import commands
from discord import app_commands
from collections import deque
import json
import logging
import os
from typing import Optional, Dict, Any

# Local imports
from bin.cogs.music.music_cog import MusicCog

logger = logging.getLogger('discord_bot.music.admin')

class ElevatedMusicCommands(commands.Cog):
    """Admin-level commands for controlling music functionality."""
    
    def __init__(self, bot: commands.Bot, music_cog: MusicCog):
        """
        Initialize elevated music commands.
        
        Args:
            bot: The Discord bot instance
            music_cog: The main MusicCog instance for music playback
        """
        self.bot = bot
        self.music_cog = music_cog
        super().__init__()
        self.config_file = "music_config.json"
        self.config: Dict[str, Any] = {}
        self.load_config()
        logger.info("ElevatedMusicCommands cog initialized")

    def load_config(self) -> None:
        """Load music role configuration from file."""
        try:
            if not os.path.exists(self.config_file):
                self.config = {}
                self.save_config()
                return
                
            with open(self.config_file, "r") as f:
                file_content = f.read().strip()
                if file_content:
                    self.config = json.loads(file_content)
                else:
                    self.config = {}
                    self.save_config()
        except json.JSONDecodeError:
            logger.error(f"Error: {self.config_file} contains invalid JSON. Using empty configuration.")
            self.config = {}
        except Exception as e:
            logger.error(f"Error loading music config: {e}")
            self.config = {}

    def save_config(self) -> None:
        """Save music role configuration to file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving music config: {e}")

    @app_commands.command(name="setmusicrole", description="Sets the music role for this server.")
    async def setmusicrole(self, interaction: discord.Interaction, role: discord.Role):
        """
        Set the role required for using elevated music commands.
        
        Args:
            interaction: Discord interaction
            role: Role to set as the music role
        """
        # Check if user has the required permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need 'Manage Server' permissions to use this command.", 
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.config:
            self.config[guild_id] = {}
            
        self.config[guild_id]["music_role"] = role.name
        self.save_config()
        
        embed = discord.Embed(
            title="Music Role Set",
            description=f"Music role has been set to **{role.name}**",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Usage",
            value="Users with this role can now use admin music commands like `/stop`, `/volume`, `/skip`, etc.", 
            inline=False
        )
        embed.set_footer(text=f"Set by {interaction.user.display_name}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def check_music_role(self, interaction: discord.Interaction) -> bool:
        """
        Check if the user has the required music role.
        
        Args:
            interaction: Discord interaction
            
        Returns:
            True if user has the role, False otherwise
        """
        # Always allow server administrators
        if interaction.user.guild_permissions.administrator:
            return True
            
        guild_id = str(interaction.guild.id)
        required_role_name = self.config.get(guild_id, {}).get("music_role")

        if not required_role_name:
            await interaction.response.send_message(
                "No music role is set yet. Please have an admin use `/setmusicrole` first.", 
                ephemeral=True
            )
            return False

        role = discord.utils.get(interaction.guild.roles, name=required_role_name)

        if not role:
            await interaction.response.send_message(
                f"Music role '{required_role_name}' not found.", 
                ephemeral=True
            )
            return False

        if role in interaction.user.roles:
            return True
        else:
            await interaction.response.send_message(
                f"You need the '{required_role_name}' role to use this command.", 
                ephemeral=True
            )
            return False

    @app_commands.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction):
        """
        Stop music playback, clear the queue and disconnect.
        
        Args:
            interaction: Discord interaction
        """
        if not await self.check_music_role(interaction):
            return

        voice_client = interaction.guild.voice_client
        guild_id = str(interaction.guild.id)

        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("I'm not connected to any voice channel.")
            return

        # Clear the queue before stopping
        queue_length = 0
        if guild_id in self.music_cog.song_queues:
            queue_length = len(self.music_cog.song_queues[guild_id])
            self.music_cog.song_queues[guild_id].clear()

        # Stop playback
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            
        await interaction.response.defer(thinking=True)
        
        # Disconnect
        await voice_client.disconnect()
        
        # Confirmation message
        embed = discord.Embed(
            title="Playback Stopped",
            description="✅ Stopped playback and disconnected from voice channel.",
            color=discord.Color.red()
        )
        
        if queue_length > 0:
            embed.add_field(name="Queue", value=f"Cleared {queue_length} song(s) from the queue", inline=False)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="move", description="Move a song to the front of the queue.")
    @app_commands.describe(position="The position of the song in the queue (e.g., 1, 2, 3).")
    async def move(self, interaction: discord.Interaction, position: int):
        """
        Move a song to the front of the queue.
        
        Args:
            interaction: Discord interaction
            position: Position of the song to move (1-based)
        """
        if not await self.check_music_role(interaction):
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.music_cog.song_queues or not self.music_cog.song_queues[guild_id]:
            await interaction.response.send_message("The queue is empty.")
            return

        if position <= 0 or position > len(self.music_cog.song_queues[guild_id]):
            await interaction.response.send_message(
                f"Invalid song position. Please enter a number between 1 and {len(self.music_cog.song_queues[guild_id])}.",
                ephemeral=True
            )
            return

        song_list = list(self.music_cog.song_queues[guild_id])
        moved_song = song_list.pop(position - 1)
        song_list.insert(0, moved_song)
        self.music_cog.song_queues[guild_id] = deque(song_list)

        embed = discord.Embed(
            title="Song Moved",
            description=f"Moved **{moved_song[1]}** to the front of the queue.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="volume", description="Set or get the playback volume.")
    @app_commands.describe(volume="Volume level (0-100)")
    async def volume(self, interaction: discord.Interaction, volume: Optional[int] = None):
        """
        Set or get the current playback volume.
        
        Args:
            interaction: Discord interaction
            volume: Volume level (0-100, None to get current volume)
        """
        if not await self.check_music_role(interaction):
            return

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            return await interaction.response.send_message("I'm not in a voice channel.")

        guild_id = str(interaction.guild.id)

        # Get current volume if not setting a new one
        if volume is None:
            current_volume = self.music_cog.get_guild_volume(guild_id)
            
            embed = discord.Embed(
                title="Current Volume",
                description=f"🔊 {int(current_volume * 100)}%",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)
            return

        # Validate volume range
        if 0 <= volume <= 100:
            volume_float = volume / 100.0
            self.music_cog.volumes[guild_id] = volume_float

            # Update volume of current playback if playing
            if voice_client.source:
                voice_client.source.volume = volume_float

            embed = discord.Embed(
                title="Volume Changed",
                description=f"🔊 Volume set to {volume}%",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                "Volume must be between 0 and 100.",
                ephemeral=True
            )

    @app_commands.command(name="skip", description="Skips the current playing song")
    async def skip(self, interaction: discord.Interaction):
        """
        Skip the currently playing song.
        
        Args:
            interaction: Discord interaction
        """
        if not await self.check_music_role(interaction):
            return

        voice_client = interaction.guild.voice_client
        
        if not voice_client:
            await interaction.response.send_message("I'm not connected to a voice channel.")
            return
            
        if voice_client.is_playing() or voice_client.is_paused():
            # Get current song before skipping
            guild_id = str(interaction.guild.id)
            current_song = self.music_cog.get_last_played(guild_id)
            
            # Stop current playback (will automatically play next song)
            voice_client.stop()
            
            embed = discord.Embed(
                title="Song Skipped",
                description=f"⏭️ Skipped: **{current_song[1] if current_song else 'Unknown'}**",
                color=discord.Color.blue()
            )
            
            # Add info about next song if available
            if guild_id in self.music_cog.song_queues and self.music_cog.song_queues[guild_id]:
                next_song = self.music_cog.song_queues[guild_id][0]
                embed.add_field(name="Up Next", value=f"**{next_song[1]}**", inline=False)
            else:
                embed.add_field(name="Queue", value="No more songs in queue", inline=False)
                
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("Not playing anything to skip.")

    @app_commands.command(name="shuffle", description="Shuffles the current song queue.")
    async def shuffle(self, interaction: discord.Interaction):
        """
        Shuffle the song queue.
        
        Args:
            interaction: Discord interaction
        """
        if not await self.check_music_role(interaction):
            return

        guild_id = str(interaction.guild_id)
        if guild_id not in self.music_cog.song_queues or not self.music_cog.song_queues[guild_id]:
            await interaction.response.send_message("The queue is empty.")
            return

        song_list = list(self.music_cog.song_queues[guild_id])
        queue_length = len(song_list)
        random.shuffle(song_list)
        self.music_cog.song_queues[guild_id] = deque(song_list)

        embed = discord.Embed(
            title="Queue Shuffled",
            description=f"🔀 Shuffled {queue_length} songs in the queue.",
            color=discord.Color.purple()
        )
        
        # Show first few songs in the shuffled queue
        if song_list:
            queue_preview = "\n".join(f"{i+1}. {title}" for i, (_, title) in enumerate(song_list[:5]))
            if len(song_list) > 5:
                queue_preview += f"\n... and {len(song_list) - 5} more songs"
                
            embed.add_field(name="New Queue Order", value=queue_preview, inline=False)
            
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot, music_cog: Optional[MusicCog] = None):
    """
    Setup function to register the cog with the bot.
    
    Args:
        bot: The Discord bot instance
        music_cog: The MusicCog instance
    """
    if music_cog is None:
        # Try to get the music cog if it wasn't passed
        music_cog = bot.get_cog("MusicCog")
        if music_cog is None:
            logger.error("MusicCog not found. Cannot load ElevatedMusicCommands.")
            return None
            
    cog = ElevatedMusicCommands(bot, music_cog)
    await bot.add_cog(cog)
    logger.info("Admin Music Controls Added")
    return cog