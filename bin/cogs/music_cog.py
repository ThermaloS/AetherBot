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
        self.song_queues: Dict[str, Deque[Tuple[str, str]]] = {}  # {guild_id: [(query, title), ...]}
        self.volumes: Dict[str, float] = {}  # {guild_id: volume}
        self.default_volume = 0.05  # 5%
        self.last_played: Dict[str, Tuple[str, str]] = {}  # {guild_id: (query, title)}
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
            'extract_flat': False,  # Changed from default to extract full info
            # Add more options to deal with YouTube's restrictions
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'geo_bypass': True,
            'source_address': '0.0.0.0',  # IPv6 addresses cause issues sometimes
        }
        
        try:
            print(f"Extracting info for: {query}")
            results = await self.extract_info_async(query, ydl_opts)
            
            if 'entries' in results:
                # Search result
                info = results['entries'][0]
                url = info.get('url')
                if not url:  # Sometimes 'url' is not directly available
                    print("Direct URL not found, trying alternate extraction")
                    # Try to get the video URL and re-extract
                    video_url = info.get('webpage_url')
                    if video_url:
                        results = await self.extract_info_async(video_url, ydl_opts)
                        url = results.get('url')
                
                return url, info.get('title')
            else:
                # Direct URL
                url = results.get('url')
                if not url:
                    print("Direct URL not found in results, trying formats")
                    # Try to get URL from formats
                    formats = results.get('formats', [])
                    if formats:
                        for format_item in formats:
                            if format_item.get('acodec') != 'none':
                                url = format_item.get('url')
                                if url:
                                    break
                
                return url, results.get('title')
        except Exception as e:
            print(f"Error extracting song info: {type(e).__name__}: {e}")
            return None, None

    def get_guild_volume(self, guild_id: str) -> float:
        """Gets the volume for a guild or returns the default."""
        return self.volumes.get(guild_id, self.default_volume)
    
    def get_last_played(self, guild_id: str) -> Optional[Tuple[str, str]]:
        """Gets the last played song for a guild."""
        return self.last_played.get(guild_id)
    
    def add_songs_to_queue(self, guild_id: str, songs: List[Tuple[str, str]]) -> int:
        """Add songs to the queue. Returns the number of songs added."""
        if not songs:
            return 0
            
        if guild_id not in self.song_queues:
            self.song_queues[guild_id] = deque()
            
        self.song_queues[guild_id].extend(songs)
        return len(songs)
        
    async def play_audio(
        self, 
        voice_client: discord.VoiceClient, 
        url: str, 
        title: str,
        guild_id: str, 
        channel: discord.TextChannel, 
        after_callback
    ) -> bool:
        """Plays audio from a URL with the specified volume."""
        try:
            # Debug info
            print(f"Starting playback for {title}")
            print(f"URL: {url[:50]}...")  # Only print the first part of the URL for privacy
            print(f"Voice client connected: {voice_client.is_connected()}")
            
            # Set up FFmpeg options for reliable streaming
            ffmpeg_options = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn",
            }
            
            # Create audio source with more detailed error logging
            try:
                source = discord.FFmpegPCMAudio(url, **ffmpeg_options)
                print("Successfully created FFmpegPCMAudio source")
            except Exception as ffmpeg_error:
                print(f"FFmpeg error details: {ffmpeg_error}")
                await channel.send(f"Error creating audio source: {ffmpeg_error}")
                return False
            
            # Set volume
            volume = self.get_guild_volume(guild_id)
            source = discord.PCMVolumeTransformer(source, volume=volume)
            
            # Play the audio
            try:
                voice_client.play(source, after=after_callback)
                print(f"Playback started successfully for {title}")
                await channel.send(f"Now playing: **{title}** (Volume: {int(volume * 100)}%)")
                return True
            except Exception as play_error:
                print(f"Play error details: {play_error}")
                await channel.send(f"Error playing audio: {play_error}")
                return False
                
        except discord.ClientException as e:
            print(f"Discord client exception: {e}")
            await channel.send(f"Error playing audio: {e}")
            return False
        except Exception as e:
            print(f"Unexpected playback error: {type(e).__name__}: {e}")
            await channel.send(f"An unexpected error occurred during playback: {type(e).__name__}")
            return False
        
    async def play_next_song(self, guild_id: str, interaction: discord.Interaction) -> None:
        """Plays the next song in the queue."""
        print(f"Attempting to play next song for guild {guild_id}")
        
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            print("Voice client is None, cannot play")
            return

        # Get the guild's song queue
        queue = self.song_queues.get(guild_id, deque())
        print(f"Queue length: {len(queue)}")
        
        # If queue is empty, check if RadioCog can provide more songs
        if not queue:
            print("Queue is empty, checking radio mode")
            # Radio mode code remains the same...
            
            # If queue is still empty, disconnect
            if not queue and voice_client.is_connected():
                await voice_client.disconnect()
                await interaction.channel.send("Queue finished, disconnecting.")
                return

        # Get the next song
        original_query, title = queue.popleft()
        print(f"Popped song from queue: {title}")
        
        # Store as last played for radio mode reference
        self.last_played[guild_id] = (original_query, title)
        
        # Get playable URL with more detailed error handling
        try:
            print(f"Getting playable URL for {title}")
            url, _ = await self.get_song_url(original_query)
            if not url:
                print(f"Failed to get URL for {title}")
                await interaction.channel.send(f"Failed to get playable URL for: {title}")
                # Try the next song
                asyncio.create_task(self.play_next_song(guild_id, interaction))
                return
            print(f"Successfully got URL for {title}")
        except Exception as url_error:
            print(f"Error getting URL: {url_error}")
            await interaction.channel.send(f"Error retrieving playable URL: {url_error}")
            asyncio.create_task(self.play_next_song(guild_id, interaction))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
    print("MusicCog loaded!")