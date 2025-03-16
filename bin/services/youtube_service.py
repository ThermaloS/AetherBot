import asyncio
import functools
import logging
import random
import yt_dlp
from typing import Dict, Any, Tuple, Optional, List, Set

logger = logging.getLogger('discord_bot.youtube')

class YouTubeService:
    """Service for interacting with YouTube through yt_dlp."""
    
    def __init__(self, config=None, title_processor=None):
        """
        Initialize the YouTube service.
        
        Args:
            config: Configuration object
            title_processor: Optional TitleProcessor instance for title analysis
        """
        self.config = config
        self.title_processor = title_processor
        self.default_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'default_search': 'ytsearch',
            'extract_flat': False,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'geo_bypass': True,
            'source_address': '0.0.0.0',
        }
        
        # Track recently played songs to avoid repetition
        self.recently_played: Dict[str, Set[str]] = {}  # guild_id -> set of song IDs or fingerprints
        
        # Maximum number of recent songs to remember per guild
        self.recent_history_size = 50
        
        # Prepare genre search tokens
        self.genre_search_terms = {
            "rock": ["rock music", "rock songs", "best rock"],
            "metal": ["metal music", "metal songs", "best metal"],
            "electronic": ["electronic music", "edm music", "electronic dance music"],
            "house": ["house music", "deep house", "best house music"],
            "trance": ["trance music", "uplifting trance", "vocal trance"],
            "ambient": ["ambient music", "chillout music", "downtempo"],
            "hip hop": ["hip hop music", "rap music", "best hip hop"],
            "pop": ["pop music", "top pop songs", "popular music"],
            "country": ["country music", "top country songs", "best country"],
            "jazz": ["jazz music", "best jazz", "smooth jazz"],
            "classical": ["classical music", "orchestra music", "piano classical"],
            "blues": ["blues music", "rhythm and blues", "best blues"],
            "reggae": ["reggae music", "ska music", "best reggae"],
            "folk": ["folk music", "acoustic folk", "singer songwriter"],
            "world": ["world music", "latin music", "african music"]
        }
        
        # Prepare mood search tokens
        self.mood_search_terms = {
            "energetic": ["energetic music", "upbeat music", "workout music", "party music"],
            "relaxing": ["relaxing music", "chill music", "calm music", "sleep music"],
            "happy": ["happy music", "feel good music", "uplifting music", "positive vibes"],
            "sad": ["sad music", "emotional music", "melancholic songs", "heartbreak songs"],
            "romantic": ["romantic music", "love songs", "romantic ballads"],
            "dark": ["dark music", "intense music", "aggressive music", "epic dark"],
            "focus": ["focus music", "concentration music", "study music", "work music"]
        }
    
    async def extract_info_async(self, query: str, opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract video information asynchronously."""
        ydl_opts = {**self.default_opts, **(opts or {})}
        loop = asyncio.get_running_loop()
        func = functools.partial(self._extract, query, ydl_opts)
        return await loop.run_in_executor(None, func)
    
    def _extract(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous extraction helper."""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                results = ydl.extract_info(query, download=False)
                return results
            except Exception as e:
                logger.error(f"Error in YouTube extraction: {e}")
                return {}
    
    async def get_song_url(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """Get a playable URL and title from a query."""
        try:
            logger.info(f"Getting song URL for: {query[:50]}...")
            results = await self.extract_info_async(query)
            
            if 'entries' in results and results['entries']:
                # Search result
                info = results['entries'][0]
                url = info.get('url')
                if not url:
                    # Try to get the video URL and re-extract
                    video_url = info.get('webpage_url')
                    if video_url:
                        results = await self.extract_info_async(video_url)
                        url = results.get('url')
                
                return url, info.get('title')
            else:
                # Direct URL
                url = results.get('url')
                if not url:
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
    
    async def search_songs(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for songs with a query."""
        search_query = f"ytsearch{limit}:{query}"
        try:
            logger.info(f"Searching for songs: {query[:50]}... (limit: {limit})")
            results = await self.extract_info_async(search_query)
            if results and 'entries' in results:
                return results['entries']
            return []
        except Exception as e:
            logger.error(f"Error searching songs: {e}")
            return []
    
    def record_played_song(self, guild_id: str, song_info: Dict[str, Any]):
        """
        Record a song as having been played to avoid repeating it too soon.
        
        Args:
            guild_id: Guild ID as string
            song_info: Song information containing title and/or URL
        """
        # Initialize history for guild if needed
        if guild_id not in self.recently_played:
            self.recently_played[guild_id] = set()
            
        song_set = self.recently_played[guild_id]
        
        # Get unique identifier for the song
        song_id = None
        
        # Try to use the video ID first
        if 'id' in song_info:
            song_id = song_info['id']
        elif 'webpage_url' in song_info:
            song_id = song_info['webpage_url']
        elif 'title' in song_info and self.title_processor:
            # Generate a fingerprint using the title
            song_id = self.title_processor.get_song_fingerprint(song_info['title'])
        else:
            # Skip recording if we can't identify the song
            return
            
        # Record the song
        song_set.add(song_id)
        
        # Limit the history size
        if len(song_set) > self.recent_history_size:
            # Convert to list, remove oldest items, convert back to set
            song_list = list(song_set)
            song_set.clear()
            song_set.update(song_list[-self.recent_history_size:])
    
    def was_recently_played(self, guild_id: str, song_info: Dict[str, Any]) -> bool:
        """
        Check if a song was recently played to avoid repetition.
        
        Args:
            guild_id: Guild ID as string
            song_info: Song information containing title and/or URL
            
        Returns:
            True if the song was recently played, False otherwise
        """
        if guild_id not in self.recently_played:
            return False
            
        song_set = self.recently_played[guild_id]
        
        # Get unique identifier for the song
        if 'id' in song_info:
            return song_info['id'] in song_set
        elif 'webpage_url' in song_info:
            return song_info['webpage_url'] in song_set
        elif 'title' in song_info and self.title_processor:
            # Generate a fingerprint using the title
            fingerprint = self.title_processor.get_song_fingerprint(song_info['title'])
            return fingerprint in song_set
            
        return False
        
    async def search_similar_songs(
        self, 
        title: str, 
        artist: Optional[str] = None,
        guild_id: Optional[str] = None,
        limit: int = 5, 
        exclude_urls: List[str] = None,
        genre: Optional[str] = None,
        mood: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for songs similar to the given title/artist.
        
        Args:
            title: Song title
            artist: Optional artist name
            guild_id: Optional guild ID for checking recently played songs
            limit: Maximum number of songs to return
            exclude_urls: URLs to exclude from results
            genre: Optional genre to search within
            mood: Optional mood to search within
            
        Returns:
            List of song information dictionaries
        """
        exclude_urls = exclude_urls or []
        
        # Create search query based on available info
        search_query = title
        if artist:
            # If we have an artist, make sure to include it in the search
            if artist not in search_query:
                search_query = f"{artist} {search_query}"
        
        # Add genre/mood if specified
        if genre and genre in self.genre_search_terms:
            genre_term = random.choice(self.genre_search_terms[genre])
            search_query = f"{search_query} {genre_term}"
        
        if mood and mood in self.mood_search_terms:
            mood_term = random.choice(self.mood_search_terms[mood])
            search_query = f"{search_query} {mood_term}"
        
        # Always add music-specific terms to focus on actual music content
        if "music" not in search_query.lower():
            search_query = f"{search_query} music"
            
        # Add filter terms to exclude common non-music content
        search_query = f"{search_query} -tutorial -how to -shorts"
            
        logger.info(f"Searching for similar songs to: {search_query}")
        
        try:
            # Use enhanced search query with 'EL:' for music filter
            # This instructs YouTube to prefer music content
            enhanced_query = f"ytsearch{limit+15}:EL:{search_query}"
            
            results = await self.extract_info_async(enhanced_query, {
                'extract_flat': True,
                'noplaylist': True,
            })
            
            if not results or 'entries' not in results:
                return []
                
            filtered_results = []
            for entry in results['entries']:
                url = entry.get('webpage_url')
                if not url or url in exclude_urls:
                    continue
                
                # Skip if recently played (prevent repetition)
                if guild_id and self.was_recently_played(guild_id, entry):
                    logger.debug(f"Skipping recently played song: {entry.get('title')}")
                    continue
                    
                if len(filtered_results) >= limit:
                    break
                    
                # Get more details for this entry to help with filtering
                try:
                    detailed_info = await self.extract_info_async(url, {
                        'extract_flat': True,
                        'skip_download': True,
                        'noplaylist': True,
                    })
                    
                    # Merge the detailed info with the entry
                    if detailed_info:
                        for key, value in detailed_info.items():
                            if key not in entry or not entry[key]:
                                entry[key] = value
                except Exception as detail_error:
                    logger.debug(f"Error getting details for {url}: {detail_error}")
                
                filtered_results.append(entry)
                
            return filtered_results
        except Exception as e:
            logger.error(f"Error searching similar songs: {e}")
            return []
    
    async def search_genre_radio(self, genre: str, limit: int = 5, guild_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for songs by genre for a radio station.
        
        Args:
            genre: Genre to search for
            limit: Maximum number of songs to return
            guild_id: Optional guild ID for checking recently played songs
            
        Returns:
            List of song information dictionaries
        """
        if genre not in self.genre_search_terms:
            logger.warning(f"Unknown genre: {genre}")
            return []
            
        # Get random search term for this genre
        search_term = random.choice(self.genre_search_terms[genre])
        
        # Add some randomization
        modifiers = [
            "top", "best", "greatest", "popular", "trending", "classic", "essential"
        ]
        years = ["2020s", "2010s", "2000s", "90s", "80s", "70s", "60s"]
        
        # 50% chance to add a modifier
        if random.random() > 0.5:
            search_term = f"{random.choice(modifiers)} {search_term}"
            
        # 30% chance to add a year/decade
        if random.random() > 0.7:
            search_term = f"{search_term} {random.choice(years)}"
        
        logger.info(f"Searching for genre radio: {search_term}")
        
        songs = await self.search_songs(search_term, limit + 10)
        
        # Filter results
        filtered_results = []
        for song in songs:
            # Skip recently played songs
            if guild_id and self.was_recently_played(guild_id, song):
                continue
                
            # Skip very long videos (likely compilations)
            duration = song.get('duration', 0)
            if duration and duration > 600:  # 10 minutes
                continue
                
            filtered_results.append(song)
            if len(filtered_results) >= limit:
                break
                
        return filtered_results
        
    async def search_mood_radio(self, mood: str, limit: int = 5, guild_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for songs by mood for a radio station.
        
        Args:
            mood: Mood to search for
            limit: Maximum number of songs to return
            guild_id: Optional guild ID for checking recently played songs
            
        Returns:
            List of song information dictionaries
        """
        if mood not in self.mood_search_terms:
            logger.warning(f"Unknown mood: {mood}")
            return []
            
        # Get random search term for this mood
        search_term = random.choice(self.mood_search_terms[mood])
        
        # Add some randomization
        modifiers = [
            "playlist", "mix", "songs", "tracks", "collection", "recommended"
        ]
        
        # 50% chance to add a modifier
        if random.random() > 0.5:
            search_term = f"{random.choice(modifiers)} {search_term}"
        
        logger.info(f"Searching for mood radio: {search_term}")
        
        songs = await self.search_songs(search_term, limit + 10)
        
        # Filter results
        filtered_results = []
        for song in songs:
            # Skip recently played songs
            if guild_id and self.was_recently_played(guild_id, song):
                continue
                
            # Skip very long videos (likely compilations)
            duration = song.get('duration', 0)
            if duration and duration > 600:  # 10 minutes
                continue
                
            filtered_results.append(song)
            if len(filtered_results) >= limit:
                break
                
        return filtered_results
    
    async def search_artist_radio(self, artist: str, limit: int = 5, guild_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for songs by an artist for a radio station.
        
        Args:
            artist: Artist name to search for
            limit: Maximum number of songs to return
            guild_id: Optional guild ID for checking recently played songs
            
        Returns:
            List of song information dictionaries
        """
        # Create search term
        search_term = f"{artist} songs"
            
        logger.info(f"Searching for artist radio: {search_term}")
        
        songs = await self.search_songs(search_term, limit + 10)
        
        # Filter results
        filtered_results = []
        for song in songs:
            # Verify artist name is in the title
            title = song.get('title', '')
            if artist.lower() not in title.lower():
                continue
                
            # Skip recently played songs
            if guild_id and self.was_recently_played(guild_id, song):
                continue
                
            # Skip very long videos (likely compilations)
            duration = song.get('duration', 0)
            if duration and duration > 600:  # 10 minutes
                continue
                
            filtered_results.append(song)
            if len(filtered_results) >= limit:
                break
                
        return filtered_results