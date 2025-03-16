import discord
from discord.ext import commands
from discord import app_commands
from collections import deque
import asyncio

from bin.cogs.music_cog import MusicCog

class AddSongs(commands.Cog):
    def __init__(self, bot: commands.Bot, music_cog: 'MusicCog'):
        self.bot = bot
        self.music_cog = music_cog
        super().__init__()
 
    @app_commands.command(name="play", description="Play a song (searches YouTube).")
    @app_commands.describe(song_query="Search query or URL")
    async def play(self, interaction: discord.Interaction, song_query: str):
        """Play a song from YouTube."""
        await interaction.response.defer()

        # Check if user is in a voice channel
        voice_channel = interaction.user.voice
        if voice_channel is None:
            await interaction.followup.send("You must be in a voice channel.")
            return
        voice_channel = voice_channel.channel

        # Connect to voice channel
        voice_client = interaction.guild.voice_client
        if voice_client:
            if voice_channel != voice_client.channel:
                await voice_client.disconnect(force=True)
                await asyncio.sleep(1)
                try:
                    voice_client = await voice_channel.connect()
                except Exception as e:
                    print(f"Connection error: {e}")
                    await interaction.followup.send(f"Error connecting to voice channel: {e}")
                    return
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
            try:
                voice_client = await voice_channel.connect()
            except Exception as e:
                print(f"Initial connection error: {e}")
                await interaction.followup.send(f"Error connecting to voice channel: {e}")
                return

        print(f"Voice client status - Connected: {voice_client.is_connected()}")
        
        # Process song query
        if not song_query.startswith("http"):
            song_query = f"ytsearch:{song_query}"

        ydl_opts = {
            'format': 'bestaudio/best',
            'default_search': 'ytsearch',
            'extract_flat': True,
            'playlist_items': '1',
            'noplaylist': False,
            'quiet': True,
            'no_warnings': True,
        }

        try:
            # Extract song info
            results = await self.music_cog.extract_info_async(song_query, ydl_opts)
            
            # Process results
            if results.get('_type') == 'playlist':
                first_track = results['entries'][0]
                title = first_track.get('title', "Untitled")
                original_query = results.get('webpage_url', song_query)
            elif 'entries' in results:
                first_track = results['entries'][0]
                title = first_track.get('title', "Untitled") 
                original_query = first_track.get('webpage_url', song_query)
            elif 'url' in results:
                title = results.get('title', "Untitled")
                original_query = results.get('webpage_url', song_query)
            else:
                await interaction.followup.send("No results found.")
                return

            if not original_query:
                await interaction.followup.send("Could not retrieve a playable URL for this song.")
                return

        except Exception as e:
            print(f"Error during yt_dlp extraction: {e}")
            await interaction.followup.send("An error occurred while searching for the song.")
            return

        # Add to queue and play
        guild_id = str(interaction.guild_id)
        if guild_id not in self.music_cog.song_queues:
            self.music_cog.song_queues[guild_id] = deque()

        self.music_cog.song_queues[guild_id].append((original_query, title))
        
        if voice_client.is_playing() or voice_client.is_paused():
            await interaction.followup.send(f"Added to queue: **{title}**")
        else:
            await interaction.followup.send(f"Now playing: **{title}**")
            await self.music_cog.play_next_song(guild_id, interaction)

    @app_commands.command(name="playlist", description="Enqueue an entire playlist.")
    @app_commands.describe(playlist_url="The URL of the YouTube playlist")
    async def play_playlist(self, interaction: discord.Interaction, playlist_url: str):
        """Add a YouTube playlist to the queue."""
        await interaction.response.defer()

        # Check if user is in a voice channel
        voice_channel = interaction.user.voice
        if voice_channel is None:
            await interaction.followup.send("You must be in a voice channel.")
            return
        voice_channel = voice_channel.channel

        # Connect to voice channel
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            voice_client = await voice_channel.connect()
        elif voice_channel != voice_client.channel:
            await voice_client.move_to(voice_channel)

        # YouTube-DL options for playlists
        ydl_opts = {
            'format': 'bestaudio/best',
            'extract_flat': 'in_playlist',
            'noplaylist': False,
            'quiet': True,
            'no_warnings': True,
        }

        try:
            # Extract playlist info
            results = await self.music_cog.extract_info_async(playlist_url, ydl_opts)

            if results.get('_type') == 'playlist':
                guild_id = str(interaction.guild_id)
                if guild_id not in self.music_cog.song_queues:
                    self.music_cog.song_queues[guild_id] = deque()

                # Add each track to the queue
                added_count = 0
                for entry in results['entries']:
                    if entry:
                        title = entry.get('title', 'Untitled')
                        original_query = entry.get('url', playlist_url)
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