import discord
import logging
from typing import List, Tuple, Optional

# Local imports
from bin.cogs.music.radio.radio_core import RadioCore
from bin.cogs.music.radio.recommendation_engine import RecommendationEngine
from bin.services.youtube_service import YouTubeService
from bin.utils.title_processor import TitleProcessor
from bin.cogs.music.radio.content_analyzer import ContentAnalyzer

logger = logging.getLogger('discord_bot.radio.service')

class RadioService:
    """Service for handling radio functionality and recommendations."""
    
    def __init__(self, radio_core: RadioCore, youtube_service: YouTubeService, title_processor: TitleProcessor):
        """
        Initialize the radio service.
        
        Args:
            radio_core: The RadioCore instance
            youtube_service: YouTube service for song retrieval
            title_processor: Title processor for song analysis
        """
        self.radio_core = radio_core
        self.youtube_service = youtube_service
        self.title_processor = title_processor
        self.content_analyzer = ContentAnalyzer(self.radio_core.config, self.title_processor)
        self.recommendation_engine = RecommendationEngine(youtube_service, title_processor, self.content_analyzer)
        
    async def add_similar_songs_to_queue(self, query: str, guild_id: int, channel: discord.abc.Messageable) -> List[Tuple[str, str]]:
        """
        Add one similar song to the queue based on the last played song.
        Uses randomized search strategies with flexible genre detection.
        
        Args:
            query: Original query or URL of the reference song
            guild_id: Discord guild ID
            channel: Text channel for sending messages
            
        Returns:
            List containing one (url, title) tuple added to the queue
        """
        # Skip if radio is not enabled
        if not self.radio_core.is_radio_enabled(guild_id):
            return []
        
        str_guild_id = str(guild_id)
        added_songs = []
        
        try:
            # Get and validate last played song
            last_played = self.radio_core.music_cog.get_last_played(str_guild_id)
            if not last_played or len(last_played) < 2:
                logger.warning("No last played song found")
                return []
                
            last_url, title = last_played
            
            # Add the currently playing song to history
            self.radio_core.add_to_recently_played(guild_id, last_url, title)
            
            # Find a similar song using the recommendation engine
            similar_song = await self.recommendation_engine.find_similar_song(
                title,
                query,
                guild_id,
                str_guild_id,
                self.radio_core._get_safe_title,
                self.radio_core.is_recently_played
            )
            
            # If we found a similar song, add it to the queue
            if similar_song:
                song_url, result_title = similar_song
                
                # Add to queue
                try:
                    # Add to queue
                    self.radio_core.music_cog.song_queues.setdefault(str_guild_id, []).append((song_url, result_title))
                    
                    # Extract new song info for logging
                    result_info = self.title_processor.parse_title_info(result_title)
                    result_artist = result_info.get('artist')
                    new_genres = self.content_analyzer.get_enhanced_genres(result_title, result_artist)
                    
                    # Log success with artist info and genres if available
                    safe_result = self.radio_core._get_safe_title(result_title)
                    log_msg = f"Added song: {safe_result}"
                    
                    if new_genres:
                        log_msg += f" - Genres: {', '.join(new_genres)}"
                        
                    logger.info(log_msg)
                    
                    added_songs.append((song_url, result_title))
                    
                except Exception as e:
                    logger.error(f"Error adding song to queue: {e}")
            
            return added_songs
            
        except Exception as e:
            logger.error(f"Error adding similar song: {e}", exc_info=True)
            return []