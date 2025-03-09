import discord
from discord.ext import commands
from discord import app_commands
from collections import deque

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

        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await voice_channel.connect()
        elif voice_channel != voice_client.channel:
            await voice_client.move_to(voice_channel)

        if not song_query.startswith("http"):
            song_query = f"ytsearch:{song_query}"

        ydl_opts_play = {
            'format': 'bestaudio/best',
            'default_search': 'ytsearch',
            'extract_flat': True,
            'playlist_items': '1',
            'noplaylist': False,
            'quiet': True,
            'no_warnings': True,
        }

        try:
            results = await self.music_cog.search_ytdlp_async(song_query, ydl_opts_play)

            if results.get('_type') == 'playlist':
                first_track = results['entries'][0]
                title = first_track.get('title', "Untitled")
                original_query = results.get('webpage_url', song_query)
                await interaction.followup.send(
                    f"**{title}** Added to the queue"
                )

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

        guild_id = str(interaction.guild_id)
        if guild_id not in self.music_cog.song_queues:
            self.music_cog.song_queues[guild_id] = deque()

        if voice_client.is_playing() or voice_client.is_paused():
            self.music_cog.song_queues[guild_id].append((original_query, title))
            await interaction.followup.send(f"Added to queue: **{title}**")
        else:
            self.music_cog.song_queues[guild_id].append((original_query, title))
            await self.music_cog.play_next_song(guild_id, interaction)

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
            results = await self.music_cog.search_ytdlp_async(playlist_url, ydl_opts)

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