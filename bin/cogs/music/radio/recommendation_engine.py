import random
import re
import logging
from typing import List, Dict, Any, Tuple, Set, Optional

# Local imports
from bin.services.youtube_service import YouTubeService
from bin.utils.title_processor import TitleProcessor
from bin.cogs.music.radio.content_analyzer import ContentAnalyzer

logger = logging.getLogger('discord_bot.radio.recommendation')

class RecommendationEngine:
    """Engine for generating music recommendations for radio mode."""
    
    def __init__(self, youtube_service: YouTubeService, title_processor: TitleProcessor, content_analyzer: ContentAnalyzer):
        """
        Initialize the recommendation engine.
        
        Args:
            youtube_service: YouTube service for searching and retrieving songs
            title_processor: Title processor for analyzing song titles
            content_analyzer: Content analyzer for determining genres and music content
        """
        self.youtube_service = youtube_service
        self.title_processor = title_processor
        self.content_analyzer = content_analyzer
        
    def _log_song_metadata(self, artist: str, song_title: str, genres: List[str], moods: List[str]) -> None:
        """Log detected song metadata"""
        if artist:
            logger.info(f"Detected artist: {artist}")
        if song_title:
            logger.info(f"Detected song title: {song_title}")
        if genres:
            logger.info(f"Detected genres: {', '.join(genres)}")
        if moods:
            logger.info(f"Detected moods: {', '.join(moods)}")
    
    def _generate_search_strategies(self, artist: str, song_title: str, genres: List[str], moods: List[str]) -> List[str]:
        """Generate diverse search strategies based on song metadata"""
        primary_search_queries = []
        
        # Strategy 1: Different songs by same artist
        if artist:
            exclude_term = f"-\"{song_title}\"" if song_title else ""
            primary_search_queries.append(f"{artist} songs official audio {exclude_term}")
            # Target singles rather than mixes
            primary_search_queries.append(f"{artist} single official audio {exclude_term}")
        
        # Strategy 2: Genre + music without artist name - focus on singles and tracks, not mixes
        if genres:
            for genre in genres[:2]:  
                primary_search_queries.append(f"{genre} music singles official audio -mix -compilation")
                primary_search_queries.append(f"{genre} official release -mix -compilation")
        
        # Strategy 3: Genre + "similar to" current song
        if genres and song_title:
            genre_str = genres[0]
            simple_song = ' '.join(song_title.split()[:3]) if song_title else ""
            if simple_song:
                primary_search_queries.append(f"{genre_str} songs like {simple_song} official audio -mix -compilation")
        
        # Strategy 4: Genre-specific searches - explicitly exclude mixes and compilations
        if genres:
            for genre in genres[:2]:  
                primary_search_queries.append(f"best {genre} songs 2024 official audio -mix -compilation -dj")
                primary_search_queries.append(f"new {genre} singles 2024 -mix -compilation -dj")
                if genre == "hip hop":
                    primary_search_queries.append("rap singles 2024 official audio -mix -compilation")
                elif genre == "electronic":
                    primary_search_queries.append("electronic singles official audio -mix -compilation")
                elif genre == "rock":
                    primary_search_queries.append("rock singles official audio -mix -compilation")
                elif genre == "pop":
                    primary_search_queries.append("pop singles 2024 official audio -mix -compilation")
            
        # Strategy 5: Similar artists' music - focus on individual tracks
        if artist and genres:
            genre_str = genres[0]
            primary_search_queries.append(f"{genre_str} artists like {artist} singles official audio -mix")
            primary_search_queries.append(f"if you like {artist} single tracks official audio -mix")
        
        # Strategy 6: Mood-based search - avoid compilations
        if moods and genres:
            mood_str = moods[0]
            genre_str = genres[0]
            primary_search_queries.append(f"{mood_str} {genre_str} singles official audio -mix -compilation")
        elif moods:
            mood_str = moods[0]
            primary_search_queries.append(f"{mood_str} singles official audio -mix -compilation")
        
        # Ensure we have enough strategies
        if len(primary_search_queries) < 3:
            if artist:
                primary_search_queries.append(f"artists similar to {artist} singles official audio -mix")
            if genres:
                primary_search_queries.append(f"new {genres[0]} singles 2024 -mix -compilation")
        
        # Remove duplicates
        return list(set(primary_search_queries))
    
    async def _try_search_strategies(
        self, 
        search_queries: List[str],
        str_guild_id: str,
        current_title: str,
        current_artist: str,
        current_song_title: str,
        tried_titles: Set[str],
        same_artist_count: int,
        max_same_artist: int,
        guild_id: int,
        get_safe_title_func
    ) -> Optional[Tuple[str, str]]:
        """Try all search strategies to find a valid song"""
        
        # Shuffle queries for randomness
        random.shuffle(search_queries)
        
        for query_idx, search_query in enumerate(search_queries):
            try:
                logger.info(f"Random search strategy #{query_idx+1}: {search_query}")
                
                results = await self.youtube_service.search_songs(search_query, 8)
                
                if not results:
                    logger.info(f"No results found for query: {search_query}")
                    continue
                    
                logger.info(f"Found {len(results)} results for query: {search_query}")
                
                for result in results:
                    result_title = result.get('title', '')
                    
                    # Skip already tried or invalid results
                    if not self._is_valid_result(
                        result_title, 
                        current_title, 
                        tried_titles, 
                        guild_id,
                        get_safe_title_func
                    ):
                        continue
                    
                    # Add to tried titles
                    tried_titles.add(result_title)
                    
                    # Handle same-artist logic
                    result_info = self.title_processor.parse_title_info(result_title)
                    result_artist = result_info.get('artist')
                    result_song = result_info.get('song_title')
                    
                    is_same_artist = self._is_same_artist(
                        current_artist, 
                        result_artist, 
                        current_song_title, 
                        result_song, 
                        same_artist_count, 
                        max_same_artist, 
                        query_idx
                    )
                    
                    if is_same_artist is False:  # Skip if explicitly rejected
                        continue
                    elif is_same_artist is True:  # It's a valid same-artist track
                        same_artist_count += 1
                    
                    # We've found a good match
                    song_url = result.get('url') or result.get('webpage_url')
                    
                    if song_url:
                        return song_url, result_title
                        
            except Exception as e:
                logger.error(f"Error in search strategy #{query_idx+1}: {e}")
                continue
                
        return None
    
    async def _try_fallback_strategy(
        self, 
        str_guild_id: str, 
        current_title: str, 
        tried_titles: Set[str], 
        guild_id: int,
        get_safe_title_func
    ) -> Optional[Tuple[str, str]]:
        """Try fallback strategy when all other strategies fail"""
        fallback_query = "top singles 2024 official audio -mix -compilation"
        logger.info(f"All random strategies failed, trying fallback: {fallback_query}")
        
        try:
            results = await self.youtube_service.search_songs(fallback_query, 10)
            
            if not results:
                return None
                
            logger.info(f"Found {len(results)} results for fallback query")
            
            for result in results:
                result_title = result.get('title', '')
                
                # Skip already tried or invalid results
                if not self._is_valid_result(
                    result_title, 
                    current_title, 
                    tried_titles, 
                    guild_id,
                    get_safe_title_func
                ):
                    continue
                
                # Add to tried titles
                tried_titles.add(result_title)
                
                # We've found a fallback match
                song_url = result.get('url') or result.get('webpage_url')
                
                if song_url:
                    return song_url, result_title
                    
        except Exception as e:
            logger.error(f"Error in fallback strategy: {e}")
            
        logger.warning("Could not find any suitable song to add after trying all strategies")
        return None
    
    def _is_valid_result(
        self, 
        result_title: str, 
        current_title: str, 
        tried_titles: Set[str], 
        guild_id: int,
        get_safe_title_func
    ) -> bool:
        """Check if search result is valid and not previously played"""
        # Skip if already tried
        if result_title in tried_titles:
            return False
            
        # Handle encoding in logs
        safe_result = get_safe_title_func(result_title)
        
        # Skip if it's the current song
        if current_title.lower() == result_title.lower():
            logger.info(f"Skipping current song: {safe_result}")
            return False
        
        # Skip non-music content
        if not self.content_analyzer.is_likely_music_content(result_title):
            logger.info(f"Skipping non-music content: {safe_result}")
            return False
            
        return True
    
    def _is_same_artist(
        self, 
        current_artist: str, 
        result_artist: str, 
        current_song_title: str, 
        result_song: str, 
        same_artist_count: int, 
        max_same_artist: int, 
        query_idx: int
    ) -> Optional[bool]:
        """
        Check if result is by same artist and if it should be allowed
        Returns: 
            - True if allowed same artist
            - False if rejected same artist
            - None if different artist
        """
        if not current_artist or not result_artist:
            return None
            
        if current_artist.lower() != result_artist.lower():
            return None
            
        # It is the same artist, now check if allowed
        
        # Check if it's the same song
        if (current_song_title and result_song and 
            current_song_title.lower() == result_song.lower()):
            logger.info(f"Skipping same song by same artist: {result_song}")
            return False
            
        # Check if we've played too many songs by this artist
        if same_artist_count > max_same_artist and query_idx > 0:
            logger.info(f"Skipping - too many songs by {current_artist} already: {result_song}")
            return False
            
        logger.info(f"Allowing different song by same artist: {result_song}")
        return True
    
    async def find_similar_song(
        self, 
        title: str,
        query: str,
        guild_id: int,
        str_guild_id: str,
        get_safe_title_func,
        is_recently_played_func
    ) -> Optional[Tuple[str, str]]:
        """
        Find a song similar to the provided title.
        
        Args:
            title: Title of the song to find similar recommendations for
            query: Original query or URL for the song
            guild_id: Discord guild ID
            str_guild_id: Guild ID as string
            get_safe_title_func: Function to get safe ASCII-encoded title for logging
            is_recently_played_func: Function to check if a song was recently played
            
        Returns:
            A tuple of (url, title) or None if no similar song was found
        """
        safe_title = get_safe_title_func(title)
        logger.info(f"Finding a song similar to: {safe_title}")
            
        # Get song metadata
        song_info = self.title_processor.parse_title_info(title)
        artist = song_info.get('artist')
        song_title = song_info.get('song_title')
        
        # Get genres and moods
        genres = self.content_analyzer.get_enhanced_genres(title, artist)
        moods = self.title_processor.detect_moods(title)
        
        # Log all detected info
        self._log_song_metadata(artist, song_title, genres, moods)
        
        # Generate search strategies
        search_queries = self._generate_search_strategies(artist, song_title, genres, moods)
        
        # Keep track of tried song titles and same artist count
        tried_titles = set()
        same_artist_count = 0
        max_same_artist = 3
        
        # Try all generated search strategies
        result = await self._try_search_strategies(
            search_queries, 
            str_guild_id, 
            title, 
            artist, 
            song_title, 
            tried_titles,
            same_artist_count,
            max_same_artist,
            guild_id,
            get_safe_title_func
        )
        
        if result:
            return result
        
        # Try fallback strategy if all others failed
        result = await self._try_fallback_strategy(
            str_guild_id, 
            title, 
            tried_titles, 
            guild_id,
            get_safe_title_func
        )
        
        return result