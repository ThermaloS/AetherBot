import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger('discord_bot.radio.content_analyzer')

# Define constants for genre detection
GENRE_INDICATORS = {
    "hip hop": ["hip hop", "rap", "hiphop", "trap", "drill", "boom bap"],
    "pop": ["pop", "pop music", "top 40", "chart topping"],
    "rock": ["rock", "alternative", "indie rock", "punk", "metal", "hard rock"],
    "electronic": ["electronic", "edm", "dubstep", "house", "techno", "trance", "bass", "dnb", "drum and bass"],
    "r&b": ["r&b", "rnb", "soul", "rhythm and blues"],
    "country": ["country", "folk", "americana", "bluegrass"],
    "jazz": ["jazz", "blues", "swing", "bebop"],
    "classical": ["classical", "orchestra", "symphony", "chamber music"],
    "reggae": ["reggae", "dancehall", "ska", "dub"],
    "latin": ["latin", "salsa", "reggaeton", "bachata", "cumbia"]
}

PLATFORMS_TO_GENRES = {
    "monstercat": "electronic",
    "owsla": "electronic",
    "mad decent": "electronic",
    "spinnin": "electronic",
    "anjuna": "electronic",
    "hospital records": "electronic",
    "ovo": "hip hop",
    "def jam": "hip hop",
    "aftermath": "hip hop",
    "top dawg": "hip hop",
    "ysl": "hip hop",
    "fueled by ramen": "rock",
    "epitaph": "rock",
    "roadrunner": "rock",
    "ninja tune": "electronic",
    "warp": "electronic"
}

GENRE_TERMS = [
    "hip hop", "rap", "pop", "rock", "metal", "edm", "electronic", 
    "r&b", "country", "jazz", "classical", "reggae", "latin",
    "house", "techno", "dubstep", "trap", "folk", "indie"
]

GENRE_MAPPINGS = {
    "rap": "hip hop",
    "trap": "hip hop",
    "house": "electronic",
    "techno": "electronic",
    "dubstep": "electronic",
    "edm": "electronic",
    "metal": "rock"
}

# Artist mapping for genre identification
ARTIST_GENRE_MAPPING = {
    "hip hop": ["kendrick", "drake", "j cole", "dababy", "jay-z", "kanye", "travis scott", "eminem"],
    "pop": ["taylor swift", "ariana", "justin", "ed sheeran", "billie eilish", "adele", "sia"],
    "rock": ["metallica", "iron maiden", "slayer", "nirvana", "foo fighters", "green day"],
    "electronic": ["avicii", "deadmau5", "skrillex", "tiesto", "martin garrix", "calvin harris"]
}

class ContentAnalyzer:
    """Utility class for analyzing music content."""
    
    def __init__(self, config=None, title_processor=None):
        """
        Initialize the content analyzer.
        
        Args:
            config: Optional configuration object
            title_processor: Optional TitleProcessor instance
        """
        self.config = config
        self.title_processor = title_processor
        
    def is_likely_music_content(self, title: str) -> bool:
        """
        Determine if a video title likely represents actual music content.
        
        Args:
            title: The title to check
            
        Returns:
            True if the title likely represents music, False otherwise
        """
        title_lower = title.lower()
        
        # Check for album/compilation keywords that we want to avoid
        album_indicators = [
            "full album", "complete album", "entire album", 
            "album mix", "full mixtape", "complete mixtape",
            "compilation", "greatest hits", "best of",
            "all songs", "all tracks", "discography",
            "album playlist", "complete collection",
            "mix 20", "power mix", "party mix", "edm mix",
            "dj mix", "remix compilation", "remix pack",
            "megamix", "mixtape", "nonstop", "continuous mix",
            "year mix", "summer mix", "winter mix", "spring mix", "fall mix"
        ]
        
        # Skip any content that's a full album or compilation
        for indicator in album_indicators:
            if indicator in title_lower:
                return False
        
        # Check for common music title patterns: "Artist - Title" or "Title by Artist"
        has_standard_format = " - " in title or (" by " in title and not "react" in title_lower)
        
        # Check for music indicators
        music_indicators = [
            "official audio", "official music", "official video",
            "lyrics", "audio", "explicit", "clean version",
            "ft.", "feat.", "remix", "prod. by", "prod by"
        ]
        
        has_music_indicator = any(indicator in title_lower for indicator in music_indicators)
        
        # Non-music content keywords that strongly indicate a video is not a song
        non_music_indicators = [
            "reaction", "reacts", "react to", "reacting",
            "interview", "interviewing", "speaks to", "conversation",
            "explains", "review", "reviews", "reviewing",
            "breakdown", "breaks down", "analysis",
            "talking about", "discusses", "discussing",
            "performed live", "performance at", "performs at",
            "vs.", "versus", "against",
            "loves", "hates", "feelings", "thinks",
            "first time hearing", "first listen", "reaction to",
            "behind the scenes", "making of", "studio session",
            "recap", "highlights", "best moments"
        ]
        
        # Check for non-music indicators
        for indicator in non_music_indicators:
            if indicator in title_lower:
                return False
        
        # Check for capitalization patterns that often indicate non-music content
        # Reaction/interview videos often use ALL CAPS for emotional impact
        words = title.split()
        caps_count = sum(1 for word in words if word.isupper() and len(word) > 2)
        
        # If more than 40% of significant words are ALL CAPS, it's likely clickbait
        if len(words) > 3 and caps_count / len(words) > 0.4:
            return False
        
        # Check for excessive emoji/punctuation (common in non-music content)
        emoji_count = sum(1 for char in title if ord(char) > 127)
        exclamation_count = title.count('!')
        
        if emoji_count > 3 or exclamation_count > 3:
            return False
        
        # Check for length indicators (albums are typically long)
        if any(x in title_lower for x in ["hour", "1h", "2h", "3h", "4h", "5h", "6h", 
                                         "min mix", "minute mix", "hour mix", 
                                         "extended", "long", "marathon"]):
            return False
            
        # Check for numerals that might indicate a mix (e.g., "2023 mix", "2024 mix")
        year_pattern = r'\b20\d\d\b'  # Matches years like 2023, 2024, etc.
        if re.search(year_pattern, title_lower) and ("mix" in title_lower or "set" in title_lower):
            return False
        
        # Check if title has too many artists (common in compilations/mixtapes)
        artist_indicators = [" & ", " and ", " x ", " vs ", "featuring", "feat", "ft."]
        artist_count = sum(title_lower.count(indicator) for indicator in artist_indicators)
        if artist_count > 2:  # More than 3 artists is likely a compilation
            return False
        
        # Check for artist and song format using TitleProcessor
        if self.title_processor:
            info = self.title_processor.parse_title_info(title)
            has_artist_and_song = info['artist'] and info['song_title']
        else:
            has_artist_and_song = False
        
        # Combine all checks - either standard format or has music indicator and no red flags
        return has_standard_format or has_artist_and_song or (has_music_indicator and emoji_count <= 2)

    def get_genre_from_search(self, artist: str, song_title: str = None) -> List[str]:
        """
        Use search information to determine potential genres for an artist/song.
        
        Args:
            artist: Artist name
            song_title: Optional song title
            
        Returns:
            List of potential genres
        """
        if not artist:
            return []
            
        potential_genres = set()
        
        try:
            # Convert to lowercase once for all comparisons
            artist_lower = artist.lower()
            title_lower = song_title.lower() if song_title else ""
            combined_text = f"{artist_lower} {title_lower}"
            
            # Check for genre indicators in combined text
            self._add_matching_genres(combined_text, GENRE_INDICATORS, potential_genres)
            
            # Check for platform/label indicators
            for platform, genre in PLATFORMS_TO_GENRES.items():
                if platform in combined_text and genre not in potential_genres:
                    potential_genres.add(genre)
                
        except Exception as e:
            logger.error(f"Error in genre search: {e}")
        
        return list(potential_genres)
    
    def _add_matching_genres(self, text: str, genre_map: dict, genre_set: set) -> None:
        """Helper to add matching genres to the set based on indicators"""
        for genre, indicators in genre_map.items():
            if any(indicator in text for indicator in indicators):
                genre_set.add(genre)
    
    def get_enhanced_genres(self, title: str, artist: str = None) -> List[str]:
        """
        Get enhanced genre detection using multiple methods.
        
        Args:
            title: Song title
            artist: Artist name if available
            
        Returns:
            List of detected genres
        """
        genres = set()
        title_lower = title.lower()
        
        # Method 1: Use title processor if available
        if self.title_processor:
            detected_genres = self.title_processor.detect_genres(title)
            if detected_genres:
                genres.update(detected_genres)
        
        # Method 2: Check for known artists and their genres
        if artist:
            artist_lower = artist.lower()
            for genre, artists in ARTIST_GENRE_MAPPING.items():
                if any(a in artist_lower for a in artists):
                    genres.add(genre)
        
        # Method 3: Try search-based detection if artist is available
        if artist:
            # Extract song title if possible
            song_title = self._extract_song_title(title, artist)
            
            # Use our search-based genre finder
            search_genres = self.get_genre_from_search(artist, song_title)
            if search_genres:
                genres.update(search_genres)
        
        # Method 4: Parse from metadata directly
        if not genres:
            # Look for genre terms in the title
            for term in GENRE_TERMS:
                if term in title_lower:
                    # Map certain terms to main genres for consistency
                    mapped_genre = GENRE_MAPPINGS.get(term, term)
                    genres.add(mapped_genre)
        
        # Ensure we at least have one genre for search purposes
        if not genres:
            genres.add("trending")
        
        return list(genres)
    
    def _extract_song_title(self, title: str, artist: str) -> Optional[str]:
        """Extract song title from full title if possible"""
        if " - " in title and artist in title:
            parts = title.split(" - ", 1)
            if len(parts) > 1:
                return parts[1]
        return None