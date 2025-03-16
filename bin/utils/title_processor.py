import re
import difflib
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger('discord_bot.title_processor')

class TitleProcessor:
    """Utility class for processing song titles to extract information and calculate similarity."""
    
    def __init__(self, config):
        """Initialize with configuration."""
        self.config = config
        music_config = config.get_section('music')
        
        # Load keywords and constants from config, with defaults
        self.compilation_keywords = music_config.get('compilation_keywords', [
            "compilation", "mix", "best of", "top 10", "top ten", 
            "playlist", "album mix", "full album", "megamix"
        ])
        
        self.music_keywords = music_config.get('music_keywords', [
            "music", "song", "audio", "official", "lyric", "remix"
        ])
        
        self.video_keywords = music_config.get('video_keywords', [
            "gameplay", "tutorial", "how to", "review", "unboxing", "vlog"
        ])
        
        self.genre_hints = music_config.get('genre_hints', [
            "rock", "pop", "electronic", "edm", "house", "dubstep", "hip hop", 
            "rap", "country", "jazz", "classical", "indie", "r&b", "metal", "dance"
        ])
        
        # Common patterns to clean from titles
        self.title_extra_identifiers = [
            '[official music video]', '[official video]', '[music video]', '[audio]', '[lyrics]',
            '(official music video)', '(official video)', '(music video)', '(audio)', '(lyrics)',
            '| official music video', '| official video', '| music video', '| audio', '| lyrics',
            'official music video', 'official video', 'music video', 'audio only', 'lyrics',
            '[release]', '(release)', '| release',
            '[hd]', '(hd)', '| hd', 'hd',
            '[4k]', '(4k)', '| 4k', '4k',
            '[bass boosted]', '(bass boosted)', '| bass boosted', 'bass boosted',
            '[extended]', '(extended)', '| extended', 'extended',
            '[remix]', '(remix)', '| remix',
            '[edit]', '(edit)', '| edit',
        ]
    
    def extract_core_title(self, title: str) -> str:
        """Extract the core elements of a song title for better comparison."""
        if not title:
            return ""
            
        # Convert to lowercase
        title = title.lower()
        
        # Remove common extra identifiers
        for rep in self.title_extra_identifiers:
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
    
    def calculate_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles."""
        if not title1 or not title2:
            return 0.0
            
        # Get core titles
        core_title1 = self.extract_core_title(title1)
        core_title2 = self.extract_core_title(title2)
        
        # Direct match on core title
        if core_title1 == core_title2:
            return 1.0
        
        # Check for exact substrings
        if (core_title1 in core_title2 and len(core_title1) > 10) or (core_title2 in core_title1 and len(core_title2) > 10):
            return 0.9  # Very high similarity but not exact match
        
        # Extract artists
        artist1 = self.extract_artist(title1)
        artist2 = self.extract_artist(title2)
        
        # If we could extract artists from both titles and they match
        if artist1 and artist2 and artist1.lower() == artist2.lower():
            # Get song parts if available
            song_part1 = core_title1.replace(artist1.lower(), '').strip('- ').strip()
            song_part2 = core_title2.replace(artist2.lower(), '').strip('- ').strip()
            
            if song_part1 and song_part2:
                # Use difflib for song title similarity
                song_similarity = difflib.SequenceMatcher(None, song_part1, song_part2).ratio()
                
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
                
                # Boost similarity for same artist
                return min(1.0, song_similarity + 0.3)
        
        # Fall back to overall similarity
        overall_similarity = difflib.SequenceMatcher(None, core_title1, core_title2).ratio()
        return overall_similarity
    
    def extract_artist(self, title: str) -> Optional[str]:
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
    
    def detect_genre(self, title: str) -> Optional[str]:
        """Detect music genre from title."""
        if not title:
            return None
            
        title_lower = title.lower()
        for genre in self.genre_hints:
            if genre in title_lower:
                return genre
        
        return None
    
    def is_likely_compilation(self, title: str, duration: int) -> bool:
        """Check if a video is likely a compilation or mix."""
        if not title:
            return False
            
        # Check by duration (over 10 minutes)
        if duration and duration > 600:
            return True
            
        # Check by keywords
        title_lower = title.lower()
        return any(keyword.lower() in title_lower for keyword in self.compilation_keywords)
    
    def is_likely_music(self, title: str) -> bool:
        """Check if the content is likely music rather than other video types."""
        if not title:
            return True  # Assume music if no title
            
        title_lower = title.lower()
        is_likely_music = any(keyword in title_lower for keyword in self.music_keywords)
        is_likely_video = any(keyword in title_lower for keyword in self.video_keywords)
        
        return is_likely_music or not is_likely_video