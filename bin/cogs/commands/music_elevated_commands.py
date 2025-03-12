from random import random
import discord
from discord.ext import commands
from discord import app_commands
from collections import deque
import json

from bin.cogs.music_cog import MusicCog

class ElevatedMusicCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, music_cog: 'MusicCog'):
        self.bot = bot
        self.music_cog = music_cog
        super().__init__()
        self.load_config()

    def load_config(self):
        try:
            with open("music_config.json", "r") as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {}
        except json.JSONDecodeError:
            print("Error: music_config.json contains invalid JSON. Using empty configuration.")
            self.config = {}

    def save_config(self):
        with open("music_config.json", "w") as f:
            json.dump(self.config, f, indent=4)

    @app_commands.command(name="setmusicrole", description="Sets the music role for this server.")
    async def setmusicrole(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need 'Manage Server' permissions to use this command.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.config:
            self.config[guild_id] = {}
        self.config[guild_id]["music_role"] = role.name
        self.save_config()
        await interaction.response.send_message(f"Music role set to {role.name}", ephemeral=True)

    async def check_music_role(self, interaction: discord.Interaction):
        """Checks if the user has the required music role."""
        guild_id = str(interaction.guild.id)
        required_role_name = self.config.get(guild_id, {}).get("music_role")

        if not required_role_name:
            await interaction.response.send_message("No music role is set yet. Please have an admin use `/setmusicrole` first.", ephemeral=True)
            return False  # No role set, disallow command usage

        role = discord.utils.get(interaction.guild.roles, name=required_role_name)

        if not role:
            await interaction.response.send_message(f"Music role '{required_role_name}' not found.", ephemeral=True)
            return False

        if role in interaction.user.roles:
            return True
        else:
            await interaction.response.send_message(f"You need the '{required_role_name}' role to use this command.", ephemeral=True)
            return False

    @app_commands.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction):
        if not await self.check_music_role(interaction):
            return

        voice_client = interaction.guild.voice_client
        guild_id = str(interaction.guild.id)

        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("I'm not connected to any voice channel.")
            return

        if guild_id in self.music_cog.song_queues:
            self.music_cog.song_queues[guild_id].clear()

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        await interaction.response.defer(thinking=True)
        await voice_client.disconnect()
        await interaction.followup.send("Stopped playback and disconnected!")

    @app_commands.command(name="move", description="Move a song to the front of the queue.")
    @app_commands.describe(position="The position of the song in the queue (e.g., 1, 2, 3).")
    async def move(self, interaction: discord.Interaction, position: int):
        if not await self.check_music_role(interaction):
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.music_cog.song_queues or not self.music_cog.song_queues[guild_id]:
            await interaction.response.send_message("The queue is empty.")
            return

        if position <= 0 or position > len(self.music_cog.song_queues[guild_id]):
            await interaction.response.send_message("Invalid song position.")
            return

        song_list = list(self.music_cog.song_queues[guild_id])
        moved_song = song_list.pop(position - 1)
        song_list.insert(0, moved_song)
        self.music_cog.song_queues[guild_id] = deque(song_list)

        await interaction.response.send_message(
            f"Moved '{moved_song[1]}' to the front of the queue."
        )

    @app_commands.command(name="volume", description="Set or get the playback volume.")
    @app_commands.describe(volume="Volume level (0-100)")
    async def volume(self, interaction: discord.Interaction, volume: int = None):
        if not await self.check_music_role(interaction):
            return

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            return await interaction.response.send_message("I'm not in a voice channel.")

        guild_id = str(interaction.guild.id)

        if volume is None:
            current_volume = self.music_cog.volumes.get(guild_id, 1.0)
            await interaction.response.send_message(f"Current volume: {int(current_volume * 100)}%")
            return

        if 0 <= volume <= 100:
            volume_float = volume / 100.0
            self.music_cog.volumes[guild_id] = volume_float

            if voice_client.source:
                voice_client.source.volume = volume_float

            await interaction.response.send_message(f"Volume set to {volume}%")
        else:
            await interaction.response.send_message("Volume must be between 0 and 100.")

    @app_commands.command(name="skip", description="Skips the current playing song")
    async def skip(self, interaction: discord.Interaction):
        if not await self.check_music_role(interaction):
            return

        voice_client = interaction.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message("Skipped the current song.")
        else:
            await interaction.response.send_message("Not playing anything to skip.")

    @app_commands.command(name="shuffle", description="Shuffles the current song queue.")
    async def shuffle(self, interaction: discord.Interaction):
        if not await self.check_music_role(interaction):
            return

        guild_id = str(interaction.guild_id)
        if guild_id not in self.song_queues or not self.song_queues[guild_id]:
            await interaction.response.send_message("The queue is empty.")
            return

        song_list = list(self.song_queues[guild_id])
        random.shuffle(song_list)
        self.song_queues[guild_id] = deque(song_list)

        await interaction.response.send_message("Queue shuffled!")

async def setup(bot: commands.Bot, music_cog: 'MusicCog'):
    if music_cog is None:
        print("MusicCog not found. Adding ElevatedMusicCommands without core functionality.")
        music_cog = MusicCog(bot)
        return
    
    await bot.add_cog(ElevatedMusicCommands(bot, music_cog))
    print("Admin Music Controls Added")