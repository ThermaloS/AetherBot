import discord
from discord.ext import commands
from collections import deque
import yt_dlp
import asyncio
import functools
import logging
from typing import Dict, Deque, Optional, Tuple, List, Any, Union, Callable

logger = logging.getLogger('discord_bot.music')

class MusicCog(commands.Cog):
    """A Discord bot cog for playing music from YouTube."""
    
    def __init__(self, bot: commands.Bot, config=None):
        """
        Initialize the MusicCog with bot instance and configuration.
        
        Args:
            bot: The Discord bot instance
            config: Configuration object for the bot
        """
        self.bot = bot
        self.config = config
        
        # Initialize state variables
        self.song_queues: Dict[str, Deque[Tuple[str, str]]] = {}  # {guild_id: [(query, title), ...]}
        self.volumes: Dict[str, float] = {}  # {guild_id: volume}
        
        # Track the "Now Playing" messages to update them rather than creating new ones
        self.now_playing_messages: Dict[str, Tuple[discord.TextChannel, discord.Message]] = {}
        
        # Load settings from config if available
        if config:
            music_config = config.get_section('music') if hasattr(config, 'get_section') else {}
            self.default_volume = music_config.get('default_volume', 0.05)  # 5%
        else:
            self.default_volume = 0.05
            
        self.last_played: Dict[str, Tuple[str, str]] = {}  # {guild_id: (query, title)}
        logger.info("MusicCog initialized")
        super().__init__()
    
    async def extract_info_async(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts video information asynchronously using yt_dlp.
        
        Args:
            query: Search query or URL
            ydl_opts: Options for yt_dlp
            
        Returns:
            Extracted video information
        """
        loop = asyncio.get_running_loop()
        func = functools.partial(self._extract, query, ydl_opts)
        return await loop.run_in_executor(None, func)
    
    def _extract(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper method to extract info with yt_dlp.
        
        Args:
            query: Search query or URL
            ydl_opts: Options for yt_dlp
            
        Returns:
            Extracted video information
        """
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                results = ydl.extract_info(query, download=False)
                return results
        except Exception as e:
            logger.error(f"Error during extraction: {type(e).__name__}: {e}")
            return {}
    
    def _extract_youtube_id(self, url: str) -> str:
        """
        Extract YouTube video ID from a URL or search query.
        
        Args:
            url: YouTube URL or search query
            
        Returns:
            YouTube video ID or empty string if not found
        """
        if not url:
            return ""
            
        # Handle ytsearch: prefix
        if url.startswith("ytsearch:"):
            return ""
            
        # Try to extract from YouTube URL patterns
        import re
        youtube_regex = r'(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        match = re.search(youtube_regex, url)
        
        if match:
            return match.group(1)
        return ""
    
    async def get_song_url(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Gets playable URL and title from a search query or direct URL.
        
        Args:
            query: Search query or URL
            
        Returns:
            Tuple of (url, title) or (None, None) if extraction fails
        """
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'default_search': 'ytsearch',
            'extract_flat': False,
            # Add more options to deal with YouTube's restrictions
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'geo_bypass': True,
            'source_address': '0.0.0.0',  # IPv6 addresses cause issues sometimes
        }
        
        try:
            logger.debug(f"Extracting info for: {query}")
            results = await self.extract_info_async(query, ydl_opts)
            
            if not results:
                logger.warning(f"No results found for query: {query}")
                return None, None
                
            if 'entries' in results:
                # Search result
                if not results['entries']:
                    logger.warning("Empty entries list in search results")
                    return None, None
                    
                info = results['entries'][0]
                url = info.get('url')
                if not url:  # Sometimes 'url' is not directly available
                    logger.debug("Direct URL not found, trying alternate extraction")
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
                    logger.debug("Direct URL not found in results, trying formats")
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
            logger.error(f"Error extracting song info: {type(e).__name__}: {e}")
            return None, None

    def get_guild_volume(self, guild_id: str) -> float:
        """
        Gets the volume for a guild or returns the default.
        
        Args:
            guild_id: Discord guild ID as string
            
        Returns:
            Volume level as float (0.0 to 1.0)
        """
        return self.volumes.get(guild_id, self.default_volume)
    
    def get_last_played(self, guild_id: str) -> Optional[Tuple[str, str]]:
        """
        Gets the last played song for a guild.
        
        Args:
            guild_id: Discord guild ID as string
            
        Returns:
            Tuple of (query, title) for the last played song
        """
        return self.last_played.get(guild_id)
    
    def add_songs_to_queue(self, guild_id: str, songs: List[Tuple[str, str]]) -> int:
        """
        Add songs to the queue.
        
        Args:
            guild_id: Discord guild ID as string
            songs: List of (query, title) tuples to add
            
        Returns:
            Number of songs added
        """
        if not songs:
            return 0
            
        if guild_id not in self.song_queues:
            self.song_queues[guild_id] = deque()
            
        self.song_queues[guild_id].extend(songs)
        return len(songs)
    
    def create_after_callback(
        self, 
        guild_id: str, 
        channel: discord.TextChannel,
        message: Optional[discord.Message] = None
    ) -> Callable:
        """
        Create a callback function for when a song finishes playing.
        
        Args:
            guild_id: Discord guild ID as string
            channel: Text channel to send notifications to
            message: Optional message to update with new song info
            
        Returns:
            Callback function
        """
        def after_callback(error):
            if error:
                logger.error(f"Player error: {error}")
                asyncio.run_coroutine_threadsafe(
                    channel.send(f"An error occurred during playback: {error}"),
                    self.bot.loop
                )
            
            # Schedule the next song to play
            coro = self.play_next_song(guild_id, channel, message=message)
            fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            try:
                fut.result()
            except Exception as e:
                logger.error(f"Error in after_callback: {e}")
                
        return after_callback
    
    async def update_now_playing_message(
        self,
        guild_id: str,
        title: str,
        thumbnail_url: Optional[str] = None,
        status: str = "▶️ Playing",
        color: discord.Color = discord.Color.green()
    ) -> Optional[discord.Message]:
        """
        Update or create the Now Playing message.
        
        Args:
            guild_id: Discord guild ID as string
            title: Title of the currently playing song
            thumbnail_url: URL for the thumbnail image
            status: Status text to display (e.g. "Playing", "Paused")
            color: Embed color
            
        Returns:
            Updated or new message object
        """
        if guild_id not in self.now_playing_messages:
            # No existing message for this guild
            return None
            
        try:
            channel, message = self.now_playing_messages[guild_id]
            
            # Create the updated embed
            embed = discord.Embed(
                title="Now Playing",
                description=f"**{title}**",
                color=color
            )
            
            # Add volume info
            volume = self.get_guild_volume(guild_id)
            embed.add_field(
                name="Volume", 
                value=f"🔊 {int(volume * 100)}%", 
                inline=True
            )
            
            # Add queue info if available
            if guild_id in self.song_queues and self.song_queues[guild_id]:
                next_up = self.song_queues[guild_id][0][1] if self.song_queues[guild_id] else "None"
                embed.add_field(
                    name="Up Next",
                    value=f"**{next_up}**" if next_up != "None" else "Nothing in queue",
                    inline=True
                )
                
                queue_length = len(self.song_queues[guild_id])
                if queue_length > 0:
                    embed.add_field(
                        name="Queue Length",
                        value=f"{queue_length} song{'s' if queue_length != 1 else ''}",
                        inline=True
                    )
            
            # Add thumbnail if available
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            # Add status
            embed.add_field(
                name="Status",
                value=status,
                inline=False
            )
            
            # Add command help hint
            embed.set_footer(text="Use /queue to see the full queue | Use /play to add more songs")
            
            # Update the existing message
            await message.edit(embed=embed)
            return message
            
        except discord.NotFound:
            # Message was deleted or no longer exists
            del self.now_playing_messages[guild_id]
            return None
        except Exception as e:
            logger.error(f"Error updating Now Playing message: {e}")
            return None
    
    async def create_now_playing_message(
        self,
        guild_id: str,
        channel: discord.TextChannel,
        title: str,
        thumbnail_url: Optional[str] = None
    ) -> Optional[discord.Message]:
        """
        Create a new Now Playing message.
        
        Args:
            guild_id: Discord guild ID as string
            channel: Channel to send the message to
            title: Title of the song
            thumbnail_url: URL for the thumbnail image
            
        Returns:
            The new message object
        """
        try:
            # Create the embed
            embed = discord.Embed(
                title="Now Playing",
                description=f"**{title}**",
                color=discord.Color.green()
            )
            
            # Add volume info
            volume = self.get_guild_volume(guild_id)
            embed.add_field(
                name="Volume", 
                value=f"🔊 {int(volume * 100)}%", 
                inline=True
            )
            
            # Add queue info if available
            if guild_id in self.song_queues and self.song_queues[guild_id]:
                next_up = self.song_queues[guild_id][0][1] if self.song_queues[guild_id] else "None"
                embed.add_field(
                    name="Up Next",
                    value=f"**{next_up}**" if next_up != "None" else "Nothing in queue",
                    inline=True
                )
                
                queue_length = len(self.song_queues[guild_id])
                if queue_length > 0:
                    embed.add_field(
                        name="Queue Length",
                        value=f"{queue_length} song{'s' if queue_length != 1 else ''}",
                        inline=True
                    )
            
            # Add thumbnail if available
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)
            
            # Add status
            embed.add_field(
                name="Status",
                value="▶️ Playing",
                inline=False
            )
            
            # Add command help hint
            embed.set_footer(text="Use /queue to see the full queue | Use /play to add more songs")
            
            # Send the new message
            message = await channel.send(embed=embed)
            
            # Store the message for future updates
            self.now_playing_messages[guild_id] = (channel, message)
            
            return message
            
        except Exception as e:
            logger.error(f"Error creating Now Playing message: {e}")
            return None
        
    async def play_audio(
        self, 
        voice_client: discord.VoiceClient, 
        url: str, 
        title: str,
        guild_id: str, 
        channel: discord.TextChannel, 
        after_callback: Callable,
        message: Optional[discord.Message] = None
    ) -> bool:
        """
        Plays audio from a URL with the specified volume.
        
        Args:
            voice_client: Discord voice client
            url: URL to play
            title: Title of the song
            guild_id: Discord guild ID as string
            channel: Text channel to send notifications to
            after_callback: Function to call when song finishes
            message: Optional message to update with new song info
            
        Returns:
            True if playback started successfully, False otherwise
        """
        try:
            # Debug info
            logger.info(f"Starting playback for {title}")
            logger.debug(f"URL: {url[:50]}...")  # Only print the first part of the URL for privacy
            logger.debug(f"Voice client connected: {voice_client.is_connected()}")
            
            # Set up FFmpeg options for reliable streaming
            ffmpeg_options = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn",
            }
            
            # Create audio source with more detailed error logging
            try:
                source = discord.FFmpegPCMAudio(url, **ffmpeg_options)
                logger.debug("Successfully created FFmpegPCMAudio source")
            except Exception as ffmpeg_error:
                logger.error(f"FFmpeg error details: {ffmpeg_error}")
                if message:
                    embed = discord.Embed(
                        title="Playback Error",
                        description=f"Failed to play **{title}**\nError: {ffmpeg_error}",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=embed)
                else:
                    await channel.send(f"Error creating audio source: {ffmpeg_error}")
                return False
            
            # Set volume
            volume = self.get_guild_volume(guild_id)
            source = discord.PCMVolumeTransformer(source, volume=volume)
            
            # Play the audio
            try:
                voice_client.play(source, after=after_callback)
                logger.info(f"Playback started successfully for {title}")
                
                # Get thumbnail URL if available
                youtube_id = self._extract_youtube_id(self.last_played[guild_id][0])
                thumbnail_url = f"https://img.youtube.com/vi/{youtube_id}/mqdefault.jpg" if youtube_id else None
                
                # Update the Now Playing message if it exists, or create a new one
                if guild_id in self.now_playing_messages:
                    await self.update_now_playing_message(guild_id, title, thumbnail_url)
                else:
                    await self.create_now_playing_message(guild_id, channel, title, thumbnail_url)
                    
                return True
            except Exception as play_error:
                logger.error(f"Play error details: {play_error}")
                if message:
                    embed = discord.Embed(
                        title="Playback Error",
                        description=f"Failed to play **{title}**\nError: {play_error}",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=embed)
                else:
                    await channel.send(f"Error playing audio: {play_error}")
                return False
                
        except discord.ClientException as e:
            logger.error(f"Discord client exception: {e}")
            if message:
                embed = discord.Embed(
                    title="Playback Error",
                    description=f"Discord client error: {e}",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
            else:
                await channel.send(f"Error playing audio: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected playback error: {type(e).__name__}: {e}")
            if message:
                embed = discord.Embed(
                    title="Playback Error",
                    description=f"An unexpected error occurred: {type(e).__name__}",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
            else:
                await channel.send(f"An unexpected error occurred during playback: {type(e).__name__}")
            return False
    
    # Update the pause and resume methods in associated cogs to call this
    async def update_playback_status(self, guild_id: str, status: str, color: discord.Color = discord.Color.blue()):
        """
        Update the Now Playing message with the current playback status.
        
        Args:
            guild_id: Discord guild ID as string
            status: Status text to display
            color: Color for the embed
        """
        if guild_id not in self.now_playing_messages:
            return
            
        if guild_id not in self.last_played:
            return
            
        _, title = self.last_played[guild_id]
        youtube_id = self._extract_youtube_id(self.last_played[guild_id][0])
        thumbnail_url = f"https://img.youtube.com/vi/{youtube_id}/mqdefault.jpg" if youtube_id else None
        
        await self.update_now_playing_message(guild_id, title, thumbnail_url, status, color)
        
    async def play_next_song(
        self, 
        guild_id: str, 
        channel: discord.abc.Messageable,
        message: Optional[discord.Message] = None
    ) -> None:
        """
        Plays the next song in the queue.
        
        Args:
            guild_id: Discord guild ID as string
            channel: Channel object that can send messages (TextChannel or Interaction)
            message: Optional message to update with new song info
        """
        logger.debug(f"Attempting to play next song for guild {guild_id}")
        
        # Get the appropriate guild object
        guild = None
        for g in self.bot.guilds:
            if str(g.id) == guild_id:
                guild = g
                break
                
        if not guild:
            logger.error(f"Could not find guild with ID {guild_id}")
            return
            
        voice_client = guild.voice_client
        if voice_client is None:
            logger.debug("Voice client is None, cannot play")
            if guild_id in self.now_playing_messages:
                channel, message = self.now_playing_messages[guild_id]
                embed = discord.Embed(
                    title="Playback Stopped",
                    description="No longer connected to a voice channel.",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
                del self.now_playing_messages[guild_id]
            return

        # Get the guild's song queue
        queue = self.song_queues.get(guild_id, deque())
        logger.debug(f"Queue length: {len(queue)}")
        
        # If queue is empty, check if RadioCog can provide more songs
        if not queue:
            logger.debug("Queue is empty, checking radio mode")
            
            if guild_id in self.now_playing_messages:
                channel, message = self.now_playing_messages[guild_id]
                embed = discord.Embed(
                    title="Queue Empty",
                    description="Checking radio mode...",
                    color=discord.Color.blue()
                )
                await message.edit(embed=embed)
            
            # Get the RadioCog instance if available
            radio_cog = self.bot.get_cog("RadioCog")
            
            # Check if radio mode is enabled and we have a last played song
            if radio_cog and hasattr(radio_cog, 'is_radio_enabled') and radio_cog.is_radio_enabled(int(guild_id)):
                logger.debug("Radio mode is enabled, looking for similar songs")
                last_played = self.get_last_played(guild_id)
                
                if last_played:
                    original_query, title = last_played
                    logger.debug(f"Using last played song for radio: {title}")
                    
                    # Call RadioCog's method to add similar songs
                    if hasattr(radio_cog, 'add_similar_songs_to_queue'):
                        similar_songs = await radio_cog.add_similar_songs_to_queue(
                            original_query, int(guild_id), channel)
                        
                        # If we found similar songs, refresh our queue reference
                        if similar_songs:
                            queue = self.song_queues.get(guild_id, deque())
                            logger.debug(f"Radio added {len(similar_songs)} songs, new queue length: {len(queue)}")
            
            # If queue is still empty, disconnect
            if not queue and voice_client.is_connected():
                logger.debug("Queue still empty after radio check, disconnecting")
                await voice_client.disconnect()
                
                # Update Now Playing message if it exists
                if guild_id in self.now_playing_messages:
                    channel, message = self.now_playing_messages[guild_id]
                    embed = discord.Embed(
                        title="Queue Finished",
                        description="No more songs in queue. Disconnected from voice channel.",
                        color=discord.Color.gold()
                    )
                    await message.edit(embed=embed)
                else:
                    await channel.send("Queue finished, disconnecting.")
                return

        # Get the next song
        if not queue:
            logger.warning("Attempted to play next song but queue is empty")
            return
            
        original_query, title = queue.popleft()
        logger.debug(f"Popped song from queue: {title}")
        
        # Store as last played for radio mode reference
        # IMPORTANT: We store the ORIGINAL query, not the processed URL
        self.last_played[guild_id] = (original_query, title)
        
        # Get playable URL
        try:
            logger.debug(f"Getting playable URL for {title}")
            # Update loading status in Now Playing message if it exists
            if guild_id in self.now_playing_messages:
                channel, message = self.now_playing_messages[guild_id]
                youtube_id = self._extract_youtube_id(original_query)
                thumbnail_url = f"https://img.youtube.com/vi/{youtube_id}/mqdefault.jpg" if youtube_id else None
                await self.update_now_playing_message(
                    guild_id, 
                    title, 
                    thumbnail_url, 
                    "⏳ Loading...", 
                    discord.Color.blue()
                )
                
            url, _ = await self.get_song_url(original_query)
            if not url:
                logger.warning(f"Failed to get URL for {title}")
                
                # Update error in Now Playing message if it exists
                if guild_id in self.now_playing_messages:
                    channel, message = self.now_playing_messages[guild_id]
                    embed = discord.Embed(
                        title="Playback Error",
                        description=f"Failed to get playable URL for: **{title}**\nSkipping to next song...",
                        color=discord.Color.red()
                    )
                    await message.edit(embed=embed)
                else:
                    await channel.send(f"Failed to get playable URL for: {title}")
                    
                # Try the next song
                if queue:
                    asyncio.create_task(self.play_next_song(guild_id, channel))
                return
                
            logger.debug(f"Successfully got URL for {title}")
            
            # Define the callback function for when the song finishes
            after_callback = self.create_after_callback(guild_id, channel)
            
            # Play the song
            success = await self.play_audio(
                voice_client, 
                url, 
                title,
                guild_id, 
                channel, 
                after_callback
            )
            
            if not success:
                logger.warning(f"Failed to play {title}, trying next song")
                # Try the next song
                if queue:
                    asyncio.create_task(self.play_next_song(guild_id, channel))
                
        except Exception as url_error:
            logger.error(f"Error getting URL: {url_error}")
            
            # Update error in Now Playing message if it exists
            if guild_id in self.now_playing_messages:
                channel, message = self.now_playing_messages[guild_id]
                embed = discord.Embed(
                    title="Playback Error",
                    description=f"Error retrieving playable URL: {url_error}\nSkipping to next song...",
                    color=discord.Color.red()
                )
                await message.edit(embed=embed)
            else:
                await channel.send(f"Error retrieving playable URL: {url_error}")
                
            if queue:
                asyncio.create_task(self.play_next_song(guild_id, channel))
            return
    
    # Only use a single command definition (hybrid command) that works as both
    # a traditional text command and a slash command
    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Show what's currently playing")
    async def now_playing(self, ctx):
        """Display information about the currently playing song."""
        guild_id = str(ctx.guild.id)
        
        # Check if music is playing
        voice_client = ctx.guild.voice_client
        if not voice_client or not (voice_client.is_playing() or voice_client.is_paused()):
            await ctx.send("No music is currently playing.")
            return
            
        # Get the last played song
        last_played = self.last_played.get(guild_id)
        if not last_played:
            await ctx.send("No song information available.")
            return
            
        original_query, title = last_played
        youtube_id = self._extract_youtube_id(original_query)
        thumbnail_url = f"https://img.youtube.com/vi/{youtube_id}/mqdefault.jpg" if youtube_id else None
        
        # Create or update the Now Playing message
        if guild_id in self.now_playing_messages:
            channel, message = self.now_playing_messages[guild_id]
            status = "⏸️ Paused" if voice_client.is_paused() else "▶️ Playing"
            color = discord.Color.gold() if voice_client.is_paused() else discord.Color.green()
            await self.update_now_playing_message(guild_id, title, thumbnail_url, status, color)
            
            # Reply with a link to the now playing message
            await ctx.send(f"Now Playing message: {message.jump_url}")
        else:
            # Create a new Now Playing message
            await self.create_now_playing_message(guild_id, ctx.channel, title, thumbnail_url)
    
async def setup(bot: commands.Bot, config=None):
    """
    Setup function to register the cog with the bot.
    
    Args:
        bot: The Discord bot instance
        config: Optional configuration object
    """
    cog = MusicCog(bot, config)
    await bot.add_cog(cog)
    logger.info("MusicCog loaded!")
    return cog