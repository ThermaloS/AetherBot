import discord
from discord.ext import commands
from discord import app_commands
from collections import deque
import asyncio
import logging
from typing import Optional, List, Dict, Any, Union

# Local imports
from bin.cogs.music.music_cog import MusicCog

logger = logging.getLogger('discord_bot.music.play')

class AddSongs(commands.Cog):
    """Cog for adding songs to the queue and initiating playback."""
    
    def __init__(self, bot: commands.Bot, music_cog: MusicCog):
        """
        Initialize the AddSongs cog.
        
        Args:
            bot: The Discord bot instance
            music_cog: The main MusicCog instance for music playback
        """
        self.bot = bot
        self.music_cog = music_cog
        # Store message IDs for updating
        self.now_playing_messages: Dict[str, discord.Message] = {}
        super().__init__()
        logger.info("AddSongs cog initialized")
 
    @app_commands.command(name="play", description="Play a song (searches YouTube).")
    @app_commands.describe(song_query="Search query or URL")
    async def play(self, interaction: discord.Interaction, song_query: str):
        """
        Play a song from YouTube.
        
        Args:
            interaction: The Discord interaction
            song_query: Search query or URL to play
        """
        await interaction.response.defer()

        # Check if user is in a voice channel
        if not interaction.user.voice:
            await interaction.followup.send("You must be in a voice channel to use this command.")
            return
            
        voice_channel = interaction.user.voice.channel
        
        try:
            # Connect to voice channel
            voice_client = await self._ensure_voice_connection(interaction, voice_channel)
            if not voice_client:
                return
            
            logger.info(f"Voice client status - Connected: {voice_client.is_connected()}")
            
            # Process song query
            song_info = await self._process_song_query(song_query)
            if not song_info:
                await interaction.followup.send("No results found or could not retrieve playable URL.")
                return
                
            original_query, title = song_info
            
            # Add to queue and play
            guild_id = str(interaction.guild_id)
            if guild_id not in self.music_cog.song_queues:
                self.music_cog.song_queues[guild_id] = deque()

            self.music_cog.song_queues[guild_id].append((original_query, title))
            
            # Create embed for better visual response
            embed = discord.Embed(
                color=discord.Color.green(),
                title="Song Added to Queue" if voice_client.is_playing() or voice_client.is_paused() else "Now Playing"
            )
            embed.add_field(name="Song", value=f"**{title}**", inline=False)
            
            # Show thumbnail if available
            embed.set_thumbnail(url=f"https://img.youtube.com/vi/{self._extract_youtube_id(original_query)}/mqdefault.jpg")
            
            queue_position = len(self.music_cog.song_queues[guild_id])
            was_playing = voice_client.is_playing() or voice_client.is_paused()
            
            if was_playing:
                embed.description = f"Position in queue: #{queue_position}"
                message = await interaction.followup.send(embed=embed)
            else:
                embed.description = "Starting playback..."
                message = await interaction.followup.send(embed=embed)
                
                # Save the message for later updates
                self.now_playing_messages[guild_id] = message
                
                # Start playback with a reference to the message
                await self.music_cog.play_next_song(
                    guild_id, 
                    interaction.channel,
                    message=message  # Pass the message to be updated
                )
                
        except Exception as e:
            logger.error(f"Error in play command: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred: {e}")
    
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
    
    async def _ensure_voice_connection(
        self, 
        interaction: discord.Interaction, 
        voice_channel: discord.VoiceChannel
    ) -> Optional[discord.VoiceClient]:
        """
        Ensure bot is connected to the correct voice channel.
        
        Args:
            interaction: Discord interaction
            voice_channel: Voice channel to connect to
            
        Returns:
            Voice client if connected successfully, None otherwise
        """
        voice_client = interaction.guild.voice_client
        
        try:
            if voice_client:
                # Already connected
                if voice_channel == voice_client.channel:
                    return voice_client
                    
                # Connected to wrong channel
                await voice_client.disconnect(force=True)
                await asyncio.sleep(1)  # Brief delay to ensure clean disconnect
                voice_client = await voice_channel.connect()
                return voice_client
            else:
                # Not connected
                voice_client = await voice_channel.connect()
                return voice_client
                
        except Exception as e:
            logger.error(f"Voice connection error: {e}", exc_info=True)
            await interaction.followup.send(f"Error connecting to voice channel: {e}")
            return None
    
    async def _process_song_query(self, song_query: str) -> Optional[tuple]:
        """
        Process a song query to get playable information.
        
        Args:
            song_query: Search query or URL
            
        Returns:
            Tuple of (query, title) or None if processing failed
        """
        # Convert search terms to YouTube search URL if not already a URL
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
            
            if not results:
                logger.warning(f"No results found for query: {song_query}")
                return None
                
            # Process results
            if results.get('_type') == 'playlist':
                entries = results.get('entries', [])
                if not entries:
                    return None
                    
                first_track = entries[0]
                title = first_track.get('title', "Untitled")
                original_query = results.get('webpage_url', song_query)
                
            elif 'entries' in results and results['entries']:
                first_track = results['entries'][0]
                title = first_track.get('title', "Untitled") 
                original_query = first_track.get('webpage_url', song_query)
                
            elif 'url' in results or 'webpage_url' in results:
                title = results.get('title', "Untitled")
                original_query = results.get('webpage_url', song_query)
                
            else:
                logger.warning(f"Could not extract playable information from results: {results}")
                return None

            if not original_query:
                logger.warning("Could not retrieve a playable URL")
                return None
                
            return original_query, title

        except Exception as e:
            logger.error(f"Error during yt_dlp extraction: {e}", exc_info=True)
            return None

    @app_commands.command(name="playlist", description="Enqueue an entire playlist.")
    @app_commands.describe(playlist_url="The URL of the YouTube playlist")
    async def play_playlist(self, interaction: discord.Interaction, playlist_url: str):
        """
        Add a YouTube playlist to the queue.
        
        Args:
            interaction: Discord interaction
            playlist_url: URL of the playlist to add
        """
        await interaction.response.defer()

        # Check if user is in a voice channel
        if not interaction.user.voice:
            await interaction.followup.send("You must be in a voice channel to use this command.")
            return
            
        voice_channel = interaction.user.voice.channel

        try:
            # Connect to voice channel
            voice_client = await self._ensure_voice_connection(interaction, voice_channel)
            if not voice_client:
                return

            # YouTube-DL options for playlists
            ydl_opts = {
                'format': 'bestaudio/best',
                'extract_flat': 'in_playlist',
                'noplaylist': False,
                'quiet': True,
                'no_warnings': True,
            }

            # Extract playlist info
            results = await self.music_cog.extract_info_async(playlist_url, ydl_opts)
            
            if not results:
                await interaction.followup.send("No results found for this playlist.")
                return

            if results.get('_type') == 'playlist':
                guild_id = str(interaction.guild_id)
                if guild_id not in self.music_cog.song_queues:
                    self.music_cog.song_queues[guild_id] = deque()

                # Add each track to the queue
                added_count = 0
                entries = results.get('entries', [])
                playlist_title = results.get('title', 'Playlist')
                
                if not entries:
                    await interaction.followup.send("This playlist appears to be empty.")
                    return
                    
                # Create a progress embed
                embed = discord.Embed(
                    title=f"Adding Playlist: {playlist_title}",
                    description="Processing playlist tracks...",
                    color=discord.Color.blue()
                )
                message = await interaction.followup.send(embed=embed)
                
                # Add tracks to queue
                for i, entry in enumerate(entries):
                    if not entry:
                        continue
                        
                    title = entry.get('title', f'Track {i+1}')
                    original_query = entry.get('url', entry.get('webpage_url'))
                    
                    if not original_query:
                        continue
                        
                    self.music_cog.song_queues[guild_id].append((original_query, title))
                    added_count += 1
                    
                    # Update progress every 10 tracks
                    if added_count % 10 == 0:
                        embed.description = f"Added {added_count}/{len(entries)} tracks..."
                        try:
                            await message.edit(embed=embed)
                        except discord.HTTPException:
                            pass

                # Final update
                embed.title = f"Added Playlist: {playlist_title}" 
                embed.description = f"Successfully added {added_count} songs from the playlist to the queue."
                embed.color = discord.Color.green()
                
                # Add a field with a sample of tracks
                if added_count > 0:
                    sample_tracks = []
                    for i, (_, title) in enumerate(list(self.music_cog.song_queues[guild_id])[-added_count:]):
                        if i < 5:  # Show 5 sample tracks
                            sample_tracks.append(f"• {title}")
                        else:
                            break
                            
                    if sample_tracks:
                        embed.add_field(
                            name="Sample Tracks",
                            value="\n".join(sample_tracks),
                            inline=False
                        )

                await message.edit(embed=embed)
                
                # Start playing if not already playing
                if not voice_client.is_playing():
                    # Save the message for later updates
                    self.now_playing_messages[guild_id] = message
                    
                    # Start playback with reference to the message
                    await self.music_cog.play_next_song(
                        guild_id, 
                        interaction.channel,
                        message=message
                    )
            else:
                await interaction.followup.send("This doesn't seem to be a valid playlist.")
                
        except Exception as e:
            logger.error(f"Error during playlist extraction: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while processing the playlist: {e}")

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
            logger.error("MusicCog not found. Cannot load AddSongs.")
            return None
            
    cog = AddSongs(bot, music_cog)
    await bot.add_cog(cog)
    logger.info("Add Song Commands loaded!")
    return cog