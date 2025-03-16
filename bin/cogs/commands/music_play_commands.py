import discord
from discord.ext import commands
from discord import app_commands
from collections import deque
import asyncio

from bin.cogs.music_cog import MusicCog

class AddSongs(commands.Cog):
    def __init__(self, bot: commands.Bot, music_cog: 'MusicCog'):
        self.bot = bot
        self.music_cog = music_cog  # Store a reference to the MusicCog
        super().__init__()
 
    @app_commands.command(name="play", description="Play a song (searches YouTube).")
    @app_commands.describe(song_query="Search query or URL")
    async def play(self, interaction: discord.Interaction, song_query: str):
        await interaction.response.defer()

        voice_channel = interaction.user.voice
        if voice_channel is None:
            await interaction.followup.send("You must be in a voice channel.")
            return
        voice_channel = voice_channel.channel

        # Make sure we disconnect from any existing voice client before trying to connect
        voice_client = interaction.guild.voice_client
        if voice_client:
            if voice_channel != voice_client.channel:
                await voice_client.disconnect(force=True)
                # Wait briefly to ensure disconnect completes
                await asyncio.sleep(1)
                try:
                    voice_client = await voice_channel.connect()
                except Exception as e:
                    print(f"Connection error: {e}")
                    await interaction.followup.send(f"Error connecting to voice channel: {e}")
                    return
            # If already in the right channel, check connection status
            elif not voice_client.is_connected():
                await voice_client.disconnect(force=True)
                await asyncio.sleep(1)
                try:
                    voice_client = await voice_channel.connect()
                except Exception as e:
                    print(f"Reconnection error: {e}")
                    await interaction.followup.send(f"Error reconnecting to voice channel: {e}")
                    return
        else:
            # Not connected at all
            try:
                voice_client = await voice_channel.connect()
            except Exception as e:
                print(f"Initial connection error: {e}")
                await interaction.followup.send(f"Error connecting to voice channel: {e}")
                return

        print(f"Voice client status - Connected: {voice_client.is_connected()}")

    @app_commands.command(name="playlist", description="Enqueue an entire playlist.")
    @app_commands.describe(playlist_url="The URL of the YouTube playlist")
    async def play_playlist(self, interaction: discord.Interaction, playlist_url: str):
        await interaction.response.defer()

        voice_channel = interaction.user.voice
        if voice_channel is None:
            await interaction.followup.send("You must be in a voice channel.")
            return
        voice_channel = voice_channel.channel

        voice_client = interaction.guild.voice_client
        if voice_client is None:
            voice_client = await voice_channel.connect()
        elif voice_channel != voice_client.channel:
            await voice_client.move_to(voice_channel)


        ydl_opts = {
            'format': 'bestaudio/best',
            'extract_flat': 'in_playlist',  # Get all playlist entries
            'noplaylist': False,  # Allow playlists.
            'quiet': True,
            'no_warnings': True,
        }

        try:
            results = await self.music_cog.extract_info_async(playlist_url, ydl_opts)

            if results.get('_type') == 'playlist':
                guild_id = str(interaction.guild_id)
                if guild_id not in self.music_cog.song_queues:
                    self.music_cog.song_queues[guild_id] = deque()

                added_count = 0
                for entry in results['entries']:
                    if entry:  # Check if entry is valid
                        title = entry.get('title', 'Untitled')
                        original_query = entry.get('url', playlist_url)  # Use URL as original query
                        self.music_cog.song_queues[guild_id].append((original_query, title))
                        added_count += 1

                await interaction.followup.send(f"Added {added_count} songs from the playlist '{results['title']}' to the queue.")
                # Start playing if not already playing
                if not voice_client.is_playing():
                    await self.music_cog.play_next_song(guild_id, interaction)

            else:
                await interaction.followup.send("This doesn't seem to be a valid playlist.")
        except Exception as e:
            print(f"Error during playlist extraction: {e}")
            await interaction.followup.send("An error occurred while processing the playlist.")

async def setup(bot: commands.Bot, music_cog: 'MusicCog'):
    await bot.add_cog(AddSongs(bot, music_cog))
    print("Add Song Commands loaded!")