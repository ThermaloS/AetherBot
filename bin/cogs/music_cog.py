import discord
from discord.ext import commands
from collections import deque
import yt_dlp
import asyncio
from typing import Dict, Deque, Optional, Tuple, List, Any


class MusicCog(commands.Cog):
    """A Discord bot cog for playing music from YouTube."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.song_queues: Dict[int, Deque[Tuple[str, str]]] = {}  # {guild_id: [(query, title), ...]}
        self.volumes: Dict[int, float] = {}  # {guild_id: volume}
        self.default_volume = 0.05  # 5%
        super().__init__()
    
    async def _extract_info_async(self, query: str, opts: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts video information asynchronously using yt_dlp."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, 
            lambda: yt_dlp.YoutubeDL(opts).extract_info(query, download=False)
        )
    
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
            results = await self._extract_info_async(query, ydl_opts)
            
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
    
    async def find_similar_songs(self, query: str, limit: int = 3) -> List[Tuple[str, str]]:
        """Finds similar songs based on the original query."""
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'default_search': 'ytsearch',
            'extract_flat': 'in_playlist'
        }
        
        try:
            results = await self._extract_info_async(query, ydl_opts)
            
            # Handle search vs direct URL results
            if 'entries' in results:
                results = results['entries'][0]
                
            # Find related videos
            similar_songs = []
            if 'related_videos' in results:
                for related in results['related_videos'][:limit]:
                    similar_songs.append((related['webpage_url'], related['title']))
                    
            return similar_songs
        except Exception as e:
            print(f"Error finding similar songs: {e}")
            return []

    def get_guild_volume(self, guild_id: int) -> float:
        """Gets the volume for a guild or returns the default."""
        return self.volumes.get(guild_id, self.default_volume)
        
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
        """Plays the next song in the queue or disconnects if the queue is empty."""
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            return

        # Get the guild's song queue
        queue = self.song_queues.get(guild_id, deque())
        if not queue:
            # Disconnect if queue is empty
            if voice_client.is_connected():
                await voice_client.disconnect()
                await interaction.channel.send("Queue finished, disconnecting.")
            return

        # Get the next song
        original_query, title = queue.popleft()
        
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
            
            async def next_action():
                # If queue is empty, try to add similar songs
                if not self.song_queues.get(guild_id, []):
                    try:
                        similar_songs = await self.find_similar_songs(original_query)
                        if similar_songs:
                            self.song_queues.setdefault(guild_id, deque()).extend(similar_songs)
                            channel = self.bot.get_guild(guild_id).get_channel(interaction.channel_id)
                            await channel.send("Adding similar songs to the queue...")
                    except Exception as e:
                        print(f"Error adding similar songs: {e}")
                
                # Play next song or disconnect
                await self.play_next_song(guild_id, interaction)
            
            # Schedule the next action
            asyncio.run_coroutine_threadsafe(next_action(), self.bot.loop)
        
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