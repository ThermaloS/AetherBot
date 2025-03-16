import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import functools
import traceback
import random
import difflib
import re
import logging
from typing import Dict, List, Tuple, Any, Optional

from bin.cogs.music_cog import MusicCog

# Set up logging
logger = logging.getLogger('radio_cog')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class RadioCog(commands.Cog):
    """A Discord bot cog for radio-like features that automatically queue similar songs."""
    
    # Constants
    MAX_LAST_SONGS = 10
    MAX_TITLE_CACHE = 15
    SIMILARITY_THRESHOLD = 0.6  # Lowered to catch more similar songs
    LONG_VIDEO_THRESHOLD = 600  # 10 minutes
    MAX_RETRIES = 2
    
    # Keywords for filtering
    COMPILATION_KEYWORDS = [
        "compilation", "mix", "best of", "top 10", "top ten", 
        "playlist", "album mix", "full album", "megamix",
        "year mix", "mixtape", "mashup", "best songs"
    ]
    
    MUSIC_KEYWORDS = ["music", "song", "audio", "official", "lyric", "remix"]
    VIDEO_KEYWORDS = ["gameplay", "tutorial", "how to", "review", "unboxing", "vlog"]
    
    # Title cleaning patterns
    TITLE_EXTRA_IDENTIFIERS = [
        '[monstercat release]', '[monstercat]', '(monstercat release)', '(monstercat)',
        '[official music video]', '[official video]', '[music video]', '[audio]', '[lyrics]',
        '(official music video)', '(official video)', '(music video)', '(audio)', '(lyrics)',
        '| official music video', '| official video', '| music video', '| audio', '| lyrics',
        'official music video', 'official video', 'music video', 'audio only', 'lyrics',
        '[ncs release]', '(ncs release)', '[ncs]', '(ncs)', '| ncs', 'ncs',
        '[release]', '(release)', '| release',
        '[hd]', '(hd)', '| hd', 'hd',
        '[4k]', '(4k)', '| 4k', '4k',
        '[bass boosted]', '(bass boosted)', '| bass boosted', 'bass boosted',
        '[extended]', '(extended)', '| extended', 'extended',
        '[remix]', '(remix)', '| remix',
        '[edit]', '(edit)', '| edit',
        '[bootleg]', '(bootleg)', '| bootleg',
        '[cover]', '(cover)', '| cover',
        '| techno', 'techno',
        '| dubstep', 'dubstep',
        '| house', 'house',
        '| edm', 'edm',
        '| electronic', 'electronic',
        '| fanmade', 'fanmade'
    ]
    
    GENRE_HINTS = [
        "rock", "pop", "electronic", "edm", "house", "dubstep", "hip hop", 
        "rap", "country", "jazz", "classical", "indie", "r&b", "metal", "dance"
    ]
    
    def __init__(self, bot: commands.Bot, music_cog: MusicCog):
        self.bot = bot
        self.music_cog = music_cog
        self.radio_mode: Dict[int, bool] = {}  # {guild_id: is_radio_enabled}
        self.last_songs: Dict[int, List[str]] = {}  # {guild_id: [song_url1, song_url2, ...]}
        self._title_cache: Dict[int, List[Dict[str, str]]] = {}  # {guild_id: [{'url': url, 'title': title}, ...]}
        super().__init__()
        logger.info("RadioCog initialized")
    
    def is_radio_enabled(self, guild_id: int) -> bool:
        """Checks if radio mode is enabled for a guild."""
        return self.radio_mode.get(guild_id, False)
    
    async def extract_info_async(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts video information asynchronously using yt_dlp."""
        loop = asyncio.get_running_loop()
        func = functools.partial(self._extract, query, ydl_opts)
        return await loop.run_in_executor(None, func)
    
    def _extract(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Helper method to extract info with yt_dlp."""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                results = ydl.extract_info(query, download=False)
                return results
            except Exception as e:
                logger.error(f"Error in _extract: {e}")
                return {}
    
    def _extract_core_title(self, title: str) -> str:
        """Extract the core elements of a song title for better comparison."""
        # Convert to lowercase
        title = title.lower()
        
        # Remove common extra identifiers
        for rep in self.TITLE_EXTRA_IDENTIFIERS:
            title = title.replace(rep, '')
        
        # Remove brackets and their contents
        title = re.sub(r'\[.*?\]', '', title)
        title = re.sub(r'\(.*?\)', '', title)
        title = re.sub(r'\|.*?\|', '', title)
        
        # Remove special characters
        title = re.sub(r'[^\w\s\-]', '', title)
        
        # Replace multiple spaces with a single space
        title = re.sub(r'\s+', ' ', title)
        
        # Trim
        return title.strip()

    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles with better processing."""
        # Get core titles
        core_title1 = self._extract_core_title(title1)
        core_title2 = self._extract_core_title(title2)
        
        logger.debug(f"Comparing core titles: '{core_title1}' and '{core_title2}'")
        
        # Direct match on core title
        if core_title1 == core_title2:
            return 1.0
        
        # Check for exact substrings (e.g., "Virtual Riot - Embark" vs "Virtual Riot - Embark (Stealing Fire LP)")
        if (core_title1 in core_title2 and len(core_title1) > 10) or (core_title2 in core_title1 and len(core_title2) > 10):
            logger.debug(f"Found one title as substring of the other")
            return 0.9  # Very high similarity but not exact match
        
        # Extract artists
        artist1 = self._extract_artist_from_title(title1)
        artist2 = self._extract_artist_from_title(title2)
        
        # If we could extract artists from both titles and they match
        if artist1 and artist2 and artist1.lower() == artist2.lower():
            logger.debug(f"Same artist detected: {artist1}")
            
            # Get song parts if available
            song_part1 = core_title1.replace(artist1.lower(), '').strip('- ').strip()
            song_part2 = core_title2.replace(artist2.lower(), '').strip('- ').strip()
            
            if song_part1 and song_part2:
                # Use difflib for song title similarity
                song_similarity = difflib.SequenceMatcher(None, song_part1, song_part2).ratio()
                logger.debug(f"Same artist, song title similarity: {song_similarity:.2f}")
                
                # Boost similarity for same artist
                return min(1.0, song_similarity + 0.3)
        
        # Check for artist - title format and compare parts
        parts1 = core_title1.split(' - ', 1)
        parts2 = core_title2.split(' - ', 1)
        
        # If both have artist - title format
        if len(parts1) == 2 and len(parts2) == 2:
            artist1, song1 = parts1
            artist2, song2 = parts2
            
            # Same artist and very similar song title
            if artist1 == artist2:
                # Use difflib for song title similarity
                song_similarity = difflib.SequenceMatcher(None, song1, song2).ratio()
                logger.debug(f"Same artist from split, song title similarity: {song_similarity:.2f}")
                
                # Boost similarity for same artist
                return min(1.0, song_similarity + 0.3)
        
        # Fall back to overall similarity
        overall_similarity = difflib.SequenceMatcher(None, core_title1, core_title2).ratio()
        logger.debug(f"Overall similarity: {overall_similarity:.2f}")
        return overall_similarity
    
    def _extract_artist_from_title(self, title: str) -> Optional[str]:
        """Extract artist name from a title string."""
        if not title:
            return None
            
        # Format: "Artist - Title"
        if " - " in title:
            artist = title.split(" - ")[0].strip()
            # Validate artist (not empty, not too long)
            if artist and len(artist) > 1 and len(artist) < 30:
                return artist
            
        # Format: "Title [Artist Release]" or similar
        if "[" in title and "]" in title:
            parts = title.split("[")
            for part in parts:
                if "]" in part and any(x in part.lower() for x in ["release", "feat", "ft"]):
                    continue
                if "]" in part:
                    artist_candidate = part.split("]")[0].strip()
                    # Check if it looks like an artist name (not descriptive text)
                    if len(artist_candidate.split()) <= 3 and len(artist_candidate) > 2:
                        return artist_candidate
        
        # Format: "Title (feat. Artist)" or "Title ft. Artist"
        lower_title = title.lower()
        for marker in ["feat.", "ft.", "featuring"]:
            if marker in lower_title:
                parts = lower_title.split(marker, 1)
                if len(parts) > 1:
                    artist_part = parts[1].strip()
                    # Try to extract just the artist name
                    end_markers = [")", "]", "-", "|"]
                    for end_marker in end_markers:
                        if end_marker in artist_part:
                            artist_part = artist_part.split(end_marker)[0].strip()
                    
                    if len(artist_part) > 2 and len(artist_part.split()) <= 3:
                        # Use the original case from the title
                        original_idx = title.lower().find(artist_part)
                        if original_idx != -1:
                            return title[original_idx:original_idx+len(artist_part)]
                        return artist_part.title()  # Convert to title case as fallback
        
        return None
    
    def _detect_genre_from_title(self, title: str) -> Optional[str]:
        """Detect music genre from title."""
        if not title:
            return None
            
        title_lower = title.lower()
        for genre in self.GENRE_HINTS:
            if genre in title_lower:
                return genre
        
        return None
    
    def _is_likely_compilation(self, title: str, duration: int) -> bool:
        """Check if a video is likely a compilation or mix."""
        if not title:
            return False
            
        # Check by duration
        if duration and duration > self.LONG_VIDEO_THRESHOLD:
            return True
            
        # Check by keywords
        title_lower = title.lower()
        return any(keyword.lower() in title_lower for keyword in self.COMPILATION_KEYWORDS)
    
    def _is_likely_music_content(self, title: str) -> bool:
        """Check if the content is likely music rather than other video types."""
        if not title:
            return True  # Assume music if no title
            
        title_lower = title.lower()
        is_likely_music = any(keyword in title_lower for keyword in self.MUSIC_KEYWORDS)
        is_likely_video = any(keyword in title_lower for keyword in self.VIDEO_KEYWORDS)
        
        return is_likely_music or not is_likely_video
    
    def _add_to_recent_history(self, guild_id: int, url: str, title: str) -> None:
        """Add a song to recent history for a guild."""
        if not guild_id:
            return
            
        # Add to URL history
        if guild_id not in self.last_songs:
            self.last_songs[guild_id] = []
        
        self.last_songs[guild_id].append(url)
        if len(self.last_songs[guild_id]) > self.MAX_LAST_SONGS:
            self.last_songs[guild_id].pop(0)
            
        # Add to title cache
        if guild_id not in self._title_cache:
            self._title_cache[guild_id] = []
        
        self._title_cache[guild_id].append({
            'url': url,
            'title': title
        })
        
        if len(self._title_cache[guild_id]) > self.MAX_TITLE_CACHE:
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
            similarity = self._calculate_title_similarity(title, prev_title)
            
            # Log similarity for debugging
            logger.debug(f"Title similarity check: '{title}' vs '{prev_title}' = {similarity:.2f}")
            
            if similarity > self.SIMILARITY_THRESHOLD:
                logger.debug(f"Skipping similar to recently played: {title} vs {prev_title} (similarity: {similarity:.2f})")
                return True
                
        return False
    
    async def _create_search_from_title(self, title: str, limit: int = 5) -> str:
        """Create an appropriate search query from a title."""
        # Extract artist if possible
        artist = self._extract_artist_from_title(title)
        if artist and len(artist) > 2:
            logger.debug(f"Creating search query using artist: {artist}")
            return f"ytsearch{limit}:{artist} music -mix -compilation -top -best"
        
        # Extract genre if possible
        genre = self._detect_genre_from_title(title)
        if genre:
            logger.debug(f"Creating search query using genre: {genre}")
            return f"ytsearch{limit}:{genre} music -mix -compilation -top -best"
        
        # Clean and use title
        clean_title = self._extract_core_title(title)
        if clean_title and len(clean_title) > 3:
            logger.debug(f"Creating search query using cleaned title: {clean_title}")
            return f"ytsearch{limit}:{clean_title} music similar -mix -compilation -top -best"
        
        # Fallback to original title
        logger.debug(f"Creating search query using original title: {title}")
        return f"ytsearch{limit}:{title} similar music -mix -compilation -top -best"
    
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
                    
                    # Extract artist if possible for better search consistency
                    artist = self._extract_artist_from_title(title)
                    if artist:
                        logger.info(f"Using artist from title: {artist}")
                        search_query = f"ytsearch{limit+5}:{artist} music -mix -compilation -top -best"
                    else:
                        search_query = await self._create_search_from_title(title, limit + 5)
                        
                    return await self._search_by_query(search_query, title, limit, guild_id)
            
            # Fallback to generic search
            logger.info("Could not determine better search term, using generic music search")
            search_query = f"ytsearch{limit+5}:popular electronic music -mix -compilation -top -best"
            return await self._search_by_query(search_query, None, limit, guild_id)
        
        # Extract video info if it's a search query
        original_title = None
        video_url = query
        
        if query.startswith('ytsearch:'):
            try:
                logger.info(f"Processing search query: {query[:50]}...")
                search_opts = {
                    'format': 'bestaudio/best',
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True,
                    'default_search': 'ytsearch',
                    'extract_flat': False
                }
                
                search_results = await self.extract_info_async(query, search_opts)
                
                if search_results and 'entries' in search_results and search_results['entries']:
                    first_result = search_results['entries'][0]
                    video_url = first_result.get('webpage_url', '')
                    original_title = first_result.get('title', '')
                    logger.info(f"Found video URL: {video_url[:50]}...")
                    logger.info(f"Original title: {original_title}")
                    
                    # Add additional info from search results if available
                    uploader = first_result.get('uploader', '')
                    if uploader:
                        logger.info(f"Found uploader: {uploader}")
                else:
                    logger.warning("Search results empty or no entries found")
            except Exception as e:
                logger.error(f"Error converting search query: {e}")
                logger.debug(traceback.format_exc())
        
        # Search strategy prioritization
        search_strategies = [
            self._try_artist_search,  # Prioritize artist search for better genre consistency
            self._try_related_videos,
            self._try_genre_search
        ]
        
        # Try each strategy until we find songs
        for strategy in search_strategies:
            similar_songs = await strategy(video_url, original_title, limit, guild_id)
            if similar_songs:
                return similar_songs
        
        logger.warning("All search strategies failed to find similar songs")
        return []
    
    async def _try_related_videos(self, video_url: str, original_title: Optional[str], 
                                limit: int, guild_id: Optional[int]) -> List[Tuple[str, str]]:
        """Strategy 1: Try to get directly related videos."""
        if not video_url or "googlevideo.com/videoplayback" in video_url or not video_url.startswith('http'):
            logger.debug("Skipping related videos strategy due to invalid URL")
            return []
            
        logger.info(f"Trying related videos strategy for: {video_url[:50]}...")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': False,
            'skip_download': True,
            'extract_flat': False,
            'ignoreerrors': True
        }
        
        # Extract artist from the original title first if possible
        # This will help maintain genre/artist consistency
        extracted_artist = None
        if original_title:
            extracted_artist = self._extract_artist_from_title(original_title)
            if extracted_artist:
                logger.info(f"Extracted artist from original title: {extracted_artist}")
        
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"Related videos attempt {attempt + 1}")
                results = await self.extract_info_async(video_url, ydl_opts)
                
                if not results:
                    logger.debug("Empty results returned, retrying...")
                    await asyncio.sleep(1)
                    continue
                
                # If we have an artist from the original title, prioritize that
                if extracted_artist:
                    logger.info(f"Prioritizing search by extracted artist: {extracted_artist}")
                    search_query = f"ytsearch{limit+5}:{extracted_artist} music"
                    artist_results = await self._search_by_query(search_query, original_title, limit, guild_id)
                    
                    if artist_results:
                        logger.info(f"Found songs by extracted artist: {extracted_artist}")
                        return artist_results
                
                # Try using tags
                if 'tags' in results and results['tags']:
                    logger.info(f"Found {len(results['tags'])} tags")
                    top_tags = results['tags'][:3]
                    search_query = f"ytsearch{limit+5}:{' '.join(top_tags)} music"
                    
                    logger.info(f"Searching by tags: {search_query[:50]}...")
                    tag_results = await self._search_by_query(search_query, original_title, limit, guild_id)
                    
                    if tag_results:
                        return tag_results
                
                # Try using artist/channel info from the video
                if 'artist' in results or 'uploader' in results or 'channel' in results:
                    artist = results.get('artist') or results.get('uploader') or results.get('channel')
                    if artist:
                        logger.info(f"Using channel/artist from video: {artist}")
                        search_query = f"ytsearch{limit+5}:{artist} music"
                        
                        logger.info(f"Searching by artist: {search_query[:50]}...")
                        artist_results = await self._search_by_query(search_query, original_title, limit, guild_id)
                        
                        if artist_results:
                            return artist_results
                
                # Try using the video title
                if 'title' in results and results['title']:
                    title = results['title']
                    search_query = await self._create_search_from_title(title, limit + 5)
                    
                    logger.info(f"Searching by title: {search_query[:50]}...")
                    title_results = await self._search_by_query(search_query, original_title, limit, guild_id)
                    
                    if title_results:
                        return title_results
                
            except Exception as e:
                logger.error(f"Error in related videos strategy: {e}")
                logger.debug(traceback.format_exc())
            
            await asyncio.sleep(1)
        
        logger.info("Related videos strategy failed")
        return []
    
    async def _try_artist_search(self, video_url: str, original_title: Optional[str], 
                               limit: int, guild_id: Optional[int]) -> List[Tuple[str, str]]:
        """Strategy 2: Try artist-based search."""
        if not original_title:
            logger.debug("Skipping artist search strategy due to missing title")
            return []
            
        logger.info("Trying artist-based search strategy")
        artist = self._extract_artist_from_title(original_title)
        
        if artist and len(artist) > 2:
            logger.info(f"Extracted artist: {artist}")
            search_query = f"ytsearch{limit+5}:{artist} music -mix -compilation -top -best"
            return await self._search_by_query(search_query, original_title, limit, guild_id)
        
        logger.info("Artist search strategy failed (no artist found)")
        return []
    
    async def _try_genre_search(self, video_url: str, original_title: Optional[str], 
                              limit: int, guild_id: Optional[int]) -> List[Tuple[str, str]]:
        """Strategy 3: Try genre-based search."""
        logger.info("Trying genre-based search strategy")
        
        search_term = original_title or video_url
        if 'ytsearch:' in search_term:
            search_term = search_term.replace('ytsearch:', '')
        
        # Extract genre or use default
        detected_genre = self._detect_genre_from_title(search_term) or "music"
        search_query = f"ytsearch{limit+5}:{detected_genre} music -mix -compilation -top -best"
        
        logger.info(f"Genre search query: {search_query[:50]}...")
        return await self._search_by_query(search_query, original_title, limit, guild_id)
    
    async def _search_by_query(self, query: str, original_title: Optional[str], limit: int, 
                             guild_id: Optional[int]) -> List[Tuple[str, str]]:
        """Search for videos by query with improved filtering."""
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'default_search': 'ytsearch',
            'extract_flat': False
        }
        
        similar_songs = []
        
        try:
            results = await self.extract_info_async(query, ydl_opts)
            
            if results and 'entries' in results and results['entries']:
                logger.info(f"Found {len(results['entries'])} search results")
                
                # Shuffle results for variety
                entries = list(results['entries'])
                random.shuffle(entries)
                
                for entry in entries:
                    # Extract song metadata
                    title = entry.get('title', 'Unknown Title')
                    url = entry.get('url', '') or entry.get('webpage_url', '')
                    duration = entry.get('duration', 0)
                    
                    # Skip if no valid URL
                    if not url or not url.startswith('http'):
                        continue
                    
                    logger.debug(f"Evaluating - Title: {title}, Duration: {duration}s")
                    
                    # Skip if recently played
                    if self._is_recently_played(guild_id, url, title):
                        continue
                    
                    # Skip compilations, mixes, and long videos
                    if self._is_likely_compilation(title, duration):
                        logger.debug(f"Skipping likely compilation: {title}")
                        continue
                    
                    # Skip the exact original title
                    if original_title and title.lower() == original_title.lower():
                        logger.debug(f"Skipping exact match to original: {title}")
                        continue
                    
                    # Skip if it's likely a non-music video
                    if not self._is_likely_music_content(title):
                        logger.debug(f"Skipping likely non-music content: {title}")
                        continue
                    
                    # Add the song if it passes all filters
                    if url and title and len(similar_songs) < limit:
                        similar_songs.append((url, title))
                        logger.info(f"Added song: {title}")
                        
                        # Add to recently played
                        self._add_to_recent_history(guild_id, url, title)
                        
                        if len(similar_songs) >= limit:
                            break
        except Exception as e:
            logger.error(f"Error in search: {e}")
            logger.debug(traceback.format_exc())
            
        return similar_songs
    
    @app_commands.command(name="radio", description="Toggle radio mode on/off.")
    async def toggle_radio(self, interaction: discord.Interaction) -> None:
        """Toggles radio mode on/off."""
        guild_id = interaction.guild_id
        
        # Check the current state directly from the dictionary
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
            embed.description = f"Found a similar song and added it to the queue!"
            embed.color = discord.Color.green()
            embed.add_field(name="🎵 Song", value=f"**{song_title}**", inline=False)
            
            # Add a timestamp
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text="Radio mode is bringing you new music")
            
            await message.edit(embed=embed)
            
            # Return the original songs (not the formatted ones)
            return similar_songs
        except Exception as e:
            logger.error(f"Error adding similar songs: {e}")
            logger.error(traceback.format_exc())
            
            # Create an error embed
            error_embed = discord.Embed(
                title="📻 Radio Mode - Error",
                description=f"Error finding similar songs: {str(e)}",
                color=discord.Color.red()
            )
            await channel.send(embed=error_embed)
            return []


async def setup(bot: commands.Bot, music_cog: MusicCog):
    await bot.add_cog(RadioCog(bot, music_cog))
    logger.info("RadioCog loaded!")