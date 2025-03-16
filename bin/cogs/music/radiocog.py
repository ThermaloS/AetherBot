import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from typing import Dict, List, Tuple, Any, Optional

from bin.services.youtube_service import YouTubeService
from bin.utils.title_processor import TitleProcessor

# Set up logging
logger = logging.getLogger('discord_bot.radio')

class RadioCog(commands.Cog):
    """A Discord bot cog for radio-like features that automatically queue similar songs."""
    
    def __init__(self, bot: commands.Bot, music_cog, config):
        self.bot = bot
        self.music_cog = music_cog
        self.config = config
        self.youtube = YouTubeService(config)
        self.title_processor = TitleProcessor(config)
        
        # Get settings from config
        music_config = config.get_section('music')
        self.similarity_threshold = music_config.get('similarity_threshold', 0.6)
        self.max_last_songs = music_config.get('max_last_songs', 10)
        self.max_title_cache = music_config.get('max_title_cache', 15)
        
        # State
        self.radio_mode: Dict[int, bool] = {}  # {guild_id: is_radio_enabled}
        self.last_songs: Dict[int, List[str]] = {}  # {guild_id: [song_url1, song_url2, ...]}
        self._title_cache: Dict[int, List[Dict[str, str]]] = {}  # {guild_id: [{'url': url, 'title': title}, ...]}
        
        logger.info("RadioCog initialized")
    
    def is_radio_enabled(self, guild_id: int) -> bool:
        """Checks if radio mode is enabled for a guild."""
        return self.radio_mode.get(guild_id, False)
    
    def _add_to_recent_history(self, guild_id: int, url: str, title: str) -> None:
        """Add a song to recent history for a guild."""
        if not guild_id:
            return
            
        # Add to URL history
        if guild_id not in self.last_songs:
            self.last_songs[guild_id] = []
        
        self.last_songs[guild_id].append(url)
        if len(self.last_songs[guild_id]) > self.max_last_songs:
            self.last_songs[guild_id].pop(0)
            
        # Add to title cache
        if guild_id not in self._title_cache:
            self._title_cache[guild_id] = []
        
        self._title_cache[guild_id].append({
            'url': url,
            'title': title
        })
        
        if len(self._title_cache[guild_id]) > self.max_title_cache:
            self._title_cache[guild_id].pop(0)
    
    def _is_recently_played(self, guild_id: int, url: str, title: str) -> bool:
        """Check if a song was recently played."""
        if not guild_id:
            return False
            
        # Check URL
        if url in self.last_songs.get(guild_id, []):
            logger.debug(f"Skipping recently played (URL match): {title}")
            return True
            
        # Check title similarity
        for entry in self._title_cache.get(guild_id, []):
            prev_title = entry.get('title', '')
            similarity = self.title_processor.calculate_similarity(title, prev_title)
            
            if similarity > self.similarity_threshold:
                logger.debug(f"Skipping similar to recently played: {title} vs {prev_title} (similarity: {similarity:.2f})")
                return True
                
        return False
    
    async def find_similar_songs(self, query: str, limit: int = 1, guild_id: int = None) -> List[Tuple[str, str]]:
        """Finds similar songs based on the original query."""
        logger.info(f"Finding similar songs for query: {query[:50]}...")
        
        # Handle direct playback URLs
        if "googlevideo.com/videoplayback" in query:
            logger.info("Direct playback URL detected, adjusting search strategy...")
            
            # Try to find recent song metadata from the title cache
            if guild_id and guild_id in self._title_cache and self._title_cache[guild_id]:
                latest_entry = self._title_cache[guild_id][-1]
                title = latest_entry.get('title')
                if title:
                    logger.info(f"Found recent title in cache: {title}, using it instead")
                    
                    # Extract artist for better search consistency
                    artist = self.title_processor.extract_artist(title)
                    return await self._search_with_filters(title, artist, limit, guild_id)
            
            # Fallback to generic search
            logger.info("Could not determine better search term, using generic music search")
            return await self._search_with_filters("popular electronic music", None, limit, guild_id)
        
        # Extract video info if it's a search query
        original_title = None
        video_url = query
        
        if query.startswith('ytsearch:'):
            try:
                # Get the first result from the search query
                search_results = await self.youtube.extract_info_async(query, {
                    'extract_flat': False
                })
                
                if search_results and 'entries' in search_results and search_results['entries']:
                    first_result = search_results['entries'][0]
                    video_url = first_result.get('webpage_url', '')
                    original_title = first_result.get('title', '')
                    logger.info(f"Found video URL: {video_url[:50]}...")
                    logger.info(f"Original title: {original_title}")
            except Exception as e:
                logger.error(f"Error converting search query: {e}")
        
        # Extract artist from original title if available
        artist = self.title_processor.extract_artist(original_title) if original_title else None
        
        # Use artist-based search as main strategy
        if artist:
            logger.info(f"Using artist-based search with: {artist}")
            similar_songs = await self._search_with_filters(original_title, artist, limit, guild_id)
            if similar_songs:
                return similar_songs
        
        # Try by genre if artist search fails
        genre = self.title_processor.detect_genre(original_title or video_url)
        logger.info(f"Using genre-based search with: {genre or 'general music'}")
        return await self._search_with_filters(original_title or "music", genre, limit, guild_id)
    
    async def _search_with_filters(self, title: str, artist: Optional[str], 
                                limit: int, guild_id: Optional[int]) -> List[Tuple[str, str]]:
        """Search for similar songs with filtering."""
        # Get exclude URLs from recently played songs
        exclude_urls = self.last_songs.get(guild_id, []) if guild_id else []
        
        # Search for potential similar songs
        entries = await self.youtube.search_similar_songs(
            title=title,
            artist=artist,
            limit=limit + 5,  # Get a few extra to filter
            exclude_urls=exclude_urls
        )
        
        if not entries:
            return []
            
        similar_songs = []
        
        for entry in entries:
            # Extract metadata
            song_title = entry.get('title', 'Unknown Title')
            url = entry.get('webpage_url', '')
            duration = entry.get('duration', 0)
            
            if not url:
                continue
                
            # Skip if recently played
            if self._is_recently_played(guild_id, url, song_title):
                continue
                
            # Skip compilations and long videos
            if self.title_processor.is_likely_compilation(song_title, duration):
                logger.debug(f"Skipping likely compilation: {song_title}")
                continue
                
            # Skip non-music content
            if not self.title_processor.is_likely_music(song_title):
                logger.debug(f"Skipping likely non-music content: {song_title}")
                continue
                
            # Add if it passes all filters
            similar_songs.append((url, song_title))
            logger.info(f"Added song: {song_title}")
            
            # Add to recently played
            self._add_to_recent_history(guild_id, url, song_title)
            
            if len(similar_songs) >= limit:
                break
                
        return similar_songs
    
    @app_commands.command(name="radio", description="Toggle radio mode on/off.")
    async def toggle_radio(self, interaction: discord.Interaction) -> None:
        """Toggles radio mode on/off."""
        guild_id = interaction.guild_id
        
        # Check the current state
        current_state = self.radio_mode.get(guild_id, False)
        new_state = not current_state
        self.radio_mode[guild_id] = new_state
        
        # Create a nice embed for the response
        embed = discord.Embed(
            title="📻 Radio Mode",
            description=f"Radio mode is now **{'enabled' if new_state else 'disabled'}**",
            color=discord.Color.green() if new_state else discord.Color.red()
        )
        
        if new_state:
            embed.add_field(
                name="How it works",
                value="When a song finishes playing, I'll automatically find and queue a similar song.",
                inline=False
            )
            embed.add_field(
                name="Tip",
                value="Your first song sets the style for radio mode. Choose wisely!",
                inline=False
            )
        else:
            embed.add_field(
                name="Manual Mode",
                value="You'll need to manually add songs to the queue now.",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        embed.timestamp = discord.utils.utcnow()
        
        await interaction.response.send_message(embed=embed)
    
    async def add_similar_songs_to_queue(self, query: str, guild_id: int, channel: discord.TextChannel) -> List[Tuple[str, str]]:
        """Find similar songs based on the query and add them to the queue."""
        try:
            # Create a progress embed
            embed = discord.Embed(
                title="📻 Radio Mode",
                description="Looking for a similar song...",
                color=discord.Color.blue()
            )
            message = await channel.send(embed=embed)
            
            logger.info(f"Starting search for similar songs to: {query[:50]}...")
            
            # Limit to just 1 song at a time
            similar_songs = await self.find_similar_songs(query, limit=1, guild_id=guild_id)
            
            if not similar_songs:
                logger.warning("No similar songs found after all search attempts")
                # Update the embed
                embed.description = "❌ Couldn't find any similar songs."
                embed.color = discord.Color.red()
                await message.edit(embed=embed)
                return []
            
            logger.info(f"Found {len(similar_songs)} similar songs")
            
            # Format songs for queue
            formatted_songs = []
            for url, title in similar_songs:
                # If the URL is a direct googlevideo URL, convert to a search query
                if "googlevideo.com/videoplayback" in url:
                    logger.info(f"Converting direct URL to search query for: {title}")
                    formatted_songs.append((f"ytsearch:{title}", title))
                else:
                    # This should be a YouTube URL, which is good
                    formatted_songs.append((url, title))
            
            # Add songs to the queue
            logger.info(f"Calling add_songs_to_queue with guild_id: {guild_id}")
            added = self.music_cog.add_songs_to_queue(str(guild_id), formatted_songs)
            logger.info(f"Added {added} songs to queue")
            
            # Update the embed with success information
            song_title = similar_songs[0][1]
            embed.description = "Found a similar song and added it to the queue!"
            embed.color = discord.Color.green()
            embed.add_field(name="🎵 Song", value=f"**{song_title}**", inline=False)
            
            # Add a timestamp
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text="Radio mode is bringing you new music")
            
            await message.edit(embed=embed)
            
            # Return the original songs
            return similar_songs
        except Exception as e:
            logger.error(f"Error adding similar songs: {e}")
            
            # Create an error embed
            error_embed = discord.Embed(
                title="📻 Radio Mode - Error",
                description=f"Error finding similar songs: {str(e)}",
                color=discord.Color.red()
            )
            await channel.send(embed=error_embed)
            return []