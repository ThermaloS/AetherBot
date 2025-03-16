import discord
from discord.ext import commands
from collections import deque
import yt_dlp
import asyncio
import functools
from typing import Dict, Deque, Optional, Tuple, List, Any, Union


class MusicCog(commands.Cog):
    """A Discord bot cog for playing music from YouTube."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.song_queues: Dict[int, Deque[Tuple[str, str]]] = {}  # {guild_id: [(query, title), ...]}
        self.volumes: Dict[int, float] = {}  # {guild_id: volume}
        self.default_volume = 0.05  # 5%
        self.last_played: Dict[int, Tuple[str, str]] = {}  # {guild_id: (query, title)}
        super().__init__()
    
    async def extract_info_async(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts video information asynchronously using yt_dlp."""
        loop = asyncio.get_running_loop()
        func = functools.partial(self._extract, query, ydl_opts)
        return await loop.run_in_executor(None, func)
    
    def _extract(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Helper method to extract info with yt_dlp."""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(query, download=False)
            return results
    
    async def get_song_url(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """Gets playable URL and title from a search query or direct URL."""
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'default_search': 'ytsearch',
        }
        
        try:
            results = await self.extract_info_async(query, ydl_opts)
            
            if 'entries' in results:
                # Search result
                info = results['entries'][0]
                return info.get('url'), info.get('title')
            else:
                # Direct URL
                return results.get('url'), results.get('title')
        except Exception as e:
            print(f"Error extracting song info: {e}")
            return None, None

    def get_guild_volume(self, guild_id: int) -> float:
        """Gets the volume for a guild or returns the default."""
        return self.volumes.get(guild_id, self.default_volume)
    
    def get_last_played(self, guild_id: int) -> Optional[Tuple[str, str]]:
        """Gets the last played song for a guild."""
        return self.last_played.get(guild_id)
    
    def add_songs_to_queue(self, guild_id: int, songs: List[Tuple[str, str]]) -> int:
        """Add songs to the queue. Returns the number of songs added."""
        if not songs:
            return 0
            
        self.song_queues.setdefault(guild_id, deque()).extend(songs)
        return len(songs)
        
    async def play_audio(
        self, 
        voice_client: discord.VoiceClient, 
        url: str, 
        title: str,
        guild_id: int, 
        channel: discord.TextChannel, 
        after_callback
    ) -> bool:
        """Plays audio from a URL with the specified volume."""
        try:
            # Set up FFmpeg options for reliable streaming
            ffmpeg_options = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn",
            }
            
            source = discord.FFmpegPCMAudio(url, **ffmpeg_options)
            volume = self.get_guild_volume(guild_id)
            source = discord.PCMVolumeTransformer(source, volume=volume)
            
            voice_client.play(source, after=after_callback)
            await channel.send(f"Now playing: **{title}** (Volume: {int(volume * 100)}%)")
            return True
        except discord.ClientException as e:
            print(f"FFmpeg error: {e}")
            await channel.send(f"Error playing audio: {e}")
            return False
        except Exception as e:
            print(f"Unexpected playback error: {e}")
            await channel.send("An unexpected error occurred during playback.")
            return False
    
    async def play_next_song(self, guild_id: int, interaction: discord.Interaction) -> None:
        """Plays the next song in the queue."""
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            return

        # Get the guild's song queue
        queue = self.song_queues.get(guild_id, deque())
        
        # If queue is empty, check if RadioCog can provide more songs
        if not queue:
            # Try to get the RadioCog
            radio_cog = self.bot.get_cog("RadioCog")
            
            if radio_cog and radio_cog.is_radio_enabled(guild_id):
                last_song = self.get_last_played(guild_id)
                
                if last_song:
                    original_query, _ = last_song
                    similar_songs = await radio_cog.add_similar_songs_to_queue(
                        original_query, 
                        interaction.channel
                    )
                    
                    # Add the similar songs to our queue
                    if similar_songs:
                        added = self.add_songs_to_queue(guild_id, similar_songs)
                        await interaction.channel.send(f"Added {added} similar songs to the queue.")
                        # Update queue after adding songs
                        queue = self.song_queues.get(guild_id, deque())
                    else:
                        await interaction.channel.send("Couldn't find more songs for radio.")
                else:
                    # No last song to base recommendations on
                    await interaction.channel.send("No reference song for radio recommendations.")
            
            # If queue is still empty, disconnect
            if not queue and voice_client.is_connected():
                await voice_client.disconnect()
                await interaction.channel.send("Queue finished, disconnecting.")
                return

        # Get the next song
        original_query, title = queue.popleft()
        
        # Store as last played for radio mode reference
        self.last_played[guild_id] = (original_query, title)
        
        # Get playable URL
        url, _ = await self.get_song_url(original_query)
        if not url:
            await interaction.channel.send(f"Failed to get playable URL for: {title}")
            # Try the next song
            asyncio.create_task(self.play_next_song(guild_id, interaction))
            return

        # Define what happens after the song finishes
        def after_playback(error):
            if error:
                print(f"Playback error: {error}")
            
            # Schedule the next action
            asyncio.run_coroutine_threadsafe(
                self.play_next_song(guild_id, interaction), 
                self.bot.loop
            )
        
        # Try to play the song
        success = await self.play_audio(
            voice_client=voice_client,
            url=url, 
            title=title,
            guild_id=guild_id, 
            channel=interaction.channel,
            after_callback=after_playback
        )
        
        if not success:
            # Try the next song
            asyncio.create_task(self.play_next_song(guild_id, interaction))


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
    print("MusicCog loaded!")