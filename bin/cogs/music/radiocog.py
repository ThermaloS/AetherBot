import re
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
        music_config = {}
        if hasattr(config, 'get_section'):
            music_config = config.get_section('music')
        
        self.similarity_threshold = music_config.get('similarity_threshold', 0.6)
        self.max_last_songs = music_config.get('max_last_songs', 10)
        self.max_title_cache = music_config.get('max_title_cache', 15)
        
        # State
        self.radio_mode: Dict[int, bool] = {}  # {guild_id: is_radio_enabled}
        self.last_songs: Dict[int, List[str]] = {}  # {guild_id: [song_url1, song_url2, ...]}
        self._title_cache: Dict[int, List[Dict[str, str]]] = {}  # {guild_id: [{'url': url, 'title': title}, ...]}
        
        # Common music genres for better categorization
        self.music_genres = {
            "dubstep": ["dubstep", "bass", "riddim", "brostep", "bass music"],
            "edm": ["edm", "electronic", "dance", "house", "trance", "techno", "electro"],
            "trap": ["trap", "future bass", "bass house", "jersey"],
            "dnb": ["drum and bass", "dnb", "drum & bass", "jungle", "liquid"],
            "rock": ["rock", "alt rock", "alternative", "indie rock"],
            "metal": ["metal", "heavy metal", "death metal", "metalcore", "hardcore"],
            "pop": ["pop", "dance pop", "synthpop", "electropop"],
            "hip hop": ["hip hop", "rap", "trap", "r&b", "rnb"],
        }
        
        # Keywords for filtering non-music content - these are the most important to avoid
        self.non_music_keywords = [
            'how to make', 'tutorial', 'explained', 'breakdown',
            'fl studio', 'ableton', 'logic pro', 'daw',
            'in 1 minute', 'in 1 min', 'shorts', '#shorts',
            'reaction', 'reacting', 'react', 'podcast', 'interview',
        ]
        
        logger.info("RadioCog initialized with improved genre matching")
    
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
    
    def _is_likely_tutorial_or_shorts(self, title: str) -> bool:
        """
        Check if a title is likely a tutorial or shorts video.
        Much less strict than the previous implementation.
        
        Args:
            title: The video title to check
            
        Returns:
            True if likely a tutorial or shorts, False otherwise
        """
        if not title:
            return True  # Reject empty titles
            
        title_lower = title.lower()
        
        # Check for obvious non-music keywords
        for keyword in self.non_music_keywords:
            if keyword in title_lower:
                return True
        
        return False
    
    def _extract_genre(self, title: str) -> Optional[str]:
        """
        Extract music genre from title.
        
        Args:
            title: Title to extract genre from
            
        Returns:
            Genre name or None if not found
        """
        if not title:
            return None
            
        # Check for genre in brackets or parentheses
        bracket_match = re.search(r'\[(.*?)\]', title)
        paren_match = re.search(r'\((.*?)\)', title)
        
        potential_genres = []
        
        if bracket_match:
            potential_genres.append(bracket_match.group(1).lower())
        
        if paren_match:
            potential_genres.append(paren_match.group(1).lower())
        
        # Add the full title as a source
        potential_genres.append(title.lower())
        
        # Check against known genres
        for genre, keywords in self.music_genres.items():
            for potential in potential_genres:
                for keyword in keywords:
                    if keyword in potential:
                        return genre
        
        return None
    
    def _extract_artist_and_song(self, title: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract artist and song name from a title.
        
        Args:
            title: The title to parse
            
        Returns:
            Tuple of (artist, song_name) or (None, None) if extraction fails
        """
        if not title:
            return None, None
            
        # Check for "Artist - Title" format
        if " - " in title:
            parts = title.split(" - ", 1)
            artist = parts[0].strip()
            song = parts[1].strip()
            
            # Remove label/genre info from song title
            song = re.sub(r'\[[^\]]+\]|\([^)]+\)', '', song).strip()
            
            # Check if it's a reverse title with the song first
            if "official" in song.lower() and not any(term in artist.lower() for term in ["official", "audio", "music"]):
                # This might be "Song Title - Artist Name (Official Audio)"
                return artist, song
            
            return artist, song
            
        # Check for "Title by Artist" format
        match = re.search(r'(.+)\s+by\s+(.+)', title, re.IGNORECASE)
        if match:
            song = match.group(1).strip()
            artist = match.group(2).strip()
            return artist, song
            
        # If no pattern is found, return the whole title as the song
        return None, title
    
    async def find_similar_songs(self, query: str, limit: int = 1, guild_id: int = None) -> List[Tuple[str, str]]:
        """Finds similar songs based on the original query."""
        logger.info(f"Finding similar songs for query: {query[:50]}...")
        
        # Extract video info to get proper title and artist
        original_title = None
        video_id = None
        original_artist = None
        
        # Handle direct playback URLs
        if "googlevideo.com/videoplayback" in query:
            logger.info("Direct playback URL detected, checking recent song cache")
            
            # Try to find recent song metadata from the title cache
            if guild_id and guild_id in self._title_cache and self._title_cache[guild_id]:
                latest_entry = self._title_cache[guild_id][-1]
                title = latest_entry.get('title')
                if title:
                    logger.info(f"Found recent title in cache: {title}, using it for search")
                    original_title = title
                    artist, song = self._extract_artist_and_song(title)
                    if artist:
                        original_artist = artist
        
        # If it's a YouTube URL, extract the video ID
        elif "youtube.com" in query or "youtu.be" in query:
            # Extract video ID from URL
            patterns = [
                r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
                r'youtu\.be/([a-zA-Z0-9_-]{11})',
                r'youtube\.com/embed/([a-zA-Z0-9_-]{11})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, query)
                if match:
                    video_id = match.group(1)
                    break
            
            if video_id:
                try:
                    # Get the video info
                    video_info = await self.youtube.extract_info_async(f"https://www.youtube.com/watch?v={video_id}", {
                        'quiet': True,
                        'noplaylist': True
                    })
                    
                    if video_info:
                        original_title = video_info.get('title')
                        logger.info(f"Extracted title from YouTube: {original_title}")
                        
                        # Extract artist and song
                        artist, song = self._extract_artist_and_song(original_title)
                        if artist:
                            original_artist = artist
                            logger.info(f"Extracted artist: {artist}, song: {song}")
                except Exception as e:
                    logger.error(f"Error extracting video info: {e}")
        
        # If it's a search query, try to extract the search terms
        elif query.startswith('ytsearch:'):
            search_terms = query[9:]  # Remove 'ytsearch:' prefix
            logger.info(f"Using search terms: {search_terms}")
            original_title = search_terms
            
            # Try to get the actual title from search results
            try:
                search_results = await self.youtube.extract_info_async(query, {
                    'extract_flat': True
                })
                
                if search_results and 'entries' in search_results and search_results['entries']:
                    first_result = search_results['entries'][0]
                    original_title = first_result.get('title', search_terms)
                    logger.info(f"Found title from search: {original_title}")
                    
                    # Extract artist and song
                    artist, song = self._extract_artist_and_song(original_title)
                    if artist:
                        original_artist = artist
                        logger.info(f"Extracted artist: {artist}, song: {song}")
            except Exception as e:
                logger.error(f"Error extracting search results: {e}")
        
        # If we couldn't get the title, use the query as is
        if not original_title:
            logger.warning("Could not determine title, radio recommendations may be less accurate")
            return []
        
        # Extract artist if not already determined
        if not original_artist:
            original_artist = self.title_processor.extract_artist(original_title)
        
        # Extract genre
        genre = self._extract_genre(original_title)
        
        logger.info(f"Extracted artist: {original_artist or 'Unknown'}, genre: {genre or 'Unknown'}")
        
        # Build search query - make it simpler and more likely to find results
        search_queries = []
        
        # Try different search strategies
        if original_artist:
            # Strategy 1: Artist + Music
            search_queries.append(f"{original_artist} music")
            
            # Strategy 2: Artist + Genre
            if genre:
                search_queries.append(f"{original_artist} {genre}")
        
        # Strategy 3: Just use the artist name
        if original_artist:
            search_queries.append(original_artist)
        
        # Strategy 4: Use original title
        search_queries.append(original_title)
        
        # Get exclude URLs from recently played songs
        exclude_urls = self.last_songs.get(guild_id, []) if guild_id else []
        
        # Try each search strategy until we find results
        for search_query in search_queries:
            logger.info(f"Trying search query: {search_query}")
            
            # Search for potential similar songs
            entries = await self.youtube.search_similar_songs(
                title=search_query,
                artist=original_artist,
                limit=10,  # Get more to filter through
                exclude_urls=exclude_urls
            )
            
            if not entries:
                logger.warning(f"No results for search query: {search_query}")
                continue
                
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
                    
                # Skip if it's likely a tutorial or shorts
                if self._is_likely_tutorial_or_shorts(song_title):
                    logger.debug(f"Skipping tutorial/shorts: {song_title}")
                    continue
                
                # Accept this song
                similar_songs.append((url, song_title))
                logger.info(f"Added song: {song_title}")
                
                # Add to recently played
                self._add_to_recent_history(guild_id, url, song_title)
                
                if len(similar_songs) >= limit:
                    break
            
            # If we found songs with this strategy, return them
            if similar_songs:
                return similar_songs
        
        # No songs found with any strategy
        logger.warning("No similar songs found with any search strategy")
        return []
    
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
            
            # Try up to 3 times to find a suitable song
            max_attempts = 3
            for attempt in range(max_attempts):
                # Limit to just 1 song at a time
                similar_songs = await self.find_similar_songs(query, limit=1, guild_id=guild_id)
                
                if similar_songs:
                    break
                    
                if attempt < max_attempts - 1:
                    logger.info(f"No songs found on attempt {attempt+1}, trying again...")
                    embed.description = f"Looking for a similar song... (attempt {attempt+2}/{max_attempts})"
                    await message.edit(embed=embed)
            
            if not similar_songs:
                logger.warning("No similar songs found after all attempts")
                # Update the embed
                embed.description = "❌ Couldn't find any similar songs."
                embed.color = discord.Color.red()
                await message.edit(embed=embed)
                return []
            
            logger.info(f"Found {len(similar_songs)} similar songs")
            
            # Format songs for queue
            formatted_songs = []
            for url, title in similar_songs:
                # Always use the URL directly rather than converting to a search query
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