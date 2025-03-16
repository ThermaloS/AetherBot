import discord
import json
import os
import logging
from discord.ext import commands
from typing import Dict, Optional, Set, List

logger = logging.getLogger('discord_bot.radio.core')

class RadioCore(commands.Cog):
    """Core functionality for radio-like music playback (autoplay)."""
    
    def __init__(self, bot: commands.Bot, music_cog, config=None):
        """
        Initialize the radio core.
        
        Args:
            bot: The bot instance
            music_cog: The main MusicCog instance for music playback
            config: Optional configuration object
        """
        self.bot = bot
        self.music_cog = music_cog
        self.config = config
        
        # Initialize radio state
        self.radio_enabled = {}  # guild_id -> bool
        
        # Track recently played songs to avoid loops
        self.recently_played = {}  # guild_id -> deque of (url, title) tuples
        self.recently_played_max_size = 10  # Keep track of the last 10 played songs
        
        # Config file for radio settings
        self.config_file = "radio_config.json"
        self.load_config()
        
        logger.info("RadioCore initialized with history tracking")
        super().__init__()
    
    def load_config(self) -> None:
        """Load radio configuration from file."""
        try:
            if not os.path.exists(self.config_file):
                self.save_config()  # Create default config
                return
                
            with open(self.config_file, "r") as f:
                file_content = f.read().strip()
                if file_content:
                    config_data = json.loads(file_content)
                    
                    # Convert guild IDs from strings to ints
                    self.radio_enabled = {int(k): v for k, v in config_data.get('radio_enabled', {}).items()}
                else:
                    # Initialize empty config
                    self.radio_enabled = {}
        except Exception as e:
            logger.error(f"Error loading radio config: {e}")
            # Initialize empty config on error
            self.radio_enabled = {}
    
    def save_config(self) -> None:
        """Save radio configuration to file."""
        try:
            config_data = {
                'radio_enabled': {str(k): v for k, v in self.radio_enabled.items()}
            }
            
            with open(self.config_file, "w") as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving radio config: {e}")
    
    def is_radio_enabled(self, guild_id: int) -> bool:
        """
        Check if radio mode is enabled for a guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            True if radio mode is enabled, False otherwise
        """
        return self.radio_enabled.get(guild_id, False)
    
    def add_to_recently_played(self, guild_id: int, url: str, title: str) -> None:
        """
        Add a song to the recently played history for a guild.
        
        Args:
            guild_id: Discord guild ID
            url: URL of the song
            title: Title of the song
        """
        from collections import deque
        
        # Initialize if needed
        if guild_id not in self.recently_played:
            self.recently_played[guild_id] = deque(maxlen=self.recently_played_max_size)
        
        # Add to history
        self.recently_played[guild_id].append((url, title))
        logger.info(f"Added to history for guild {guild_id}: {title}")
    
    def is_recently_played(self, guild_id: int, title: str) -> bool:
        """
        Check if a song was recently played.
        
        Args:
            guild_id: Discord guild ID
            title: Song title to check
            
        Returns:
            True if the song was recently played, False otherwise
        """
        if guild_id not in self.recently_played:
            return False
        
        # Get all recent titles
        recent_titles = [rt for _, rt in self.recently_played[guild_id]]
        
        # Check for exact match
        if title in recent_titles:
            return True
        
        # Import title processor for more advanced matching
        from bin.utils.title_processor import TitleProcessor
        title_processor = TitleProcessor(self.config if self.config else {})
        
        # Check for near matches (same song different artists, etc.)
        for recent_title in recent_titles:
            # Check if they have the same song title but different artists
            info1 = title_processor.parse_title_info(title)
            info2 = title_processor.parse_title_info(recent_title)
            
            if (info1['song_title'] and info2['song_title'] and 
                info1['song_title'].lower() == info2['song_title'].lower()):
                return True
                
            # Also check using similarity
            similarity = title_processor.calculate_similarity(title, recent_title)
            if similarity > 0.8:  # High similarity threshold
                return True
                
        return False
    
    def _get_safe_title(self, title: str) -> str:
        """Get safe ASCII-encoded title for logging"""
        try:
            return title.encode('ascii', 'replace').decode('ascii')
        except:
            return title