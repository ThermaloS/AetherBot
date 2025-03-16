import re
import difflib
import logging
from typing import Optional, List, Dict, Any, Tuple, Set

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
        
        # Extended genre list for better classification
        self.genre_map = {
            # Rock genres
            "rock": ["rock", "alternative", "indie rock", "classic rock", "hard rock", "punk", "grunge"],
            "metal": ["metal", "heavy metal", "death metal", "black metal", "thrash metal", "metalcore"],
            # Electronic genres
            "electronic": ["electronic", "electronica", "edm", "techno", "house", "trance", "dubstep", "drum and bass", "dnb"],
            "house": ["house", "deep house", "progressive house", "tech house", "future house"],
            "trance": ["trance", "uplifting trance", "vocal trance", "progressive trance"],
            "ambient": ["ambient", "chill", "downtempo", "lofi", "lo-fi", "chillhop"],
            # Hip hop genres
            "hip hop": ["hip hop", "rap", "trap", "gangsta rap", "boom bap", "drill"],
            # Pop genres
            "pop": ["pop", "pop rock", "synth pop", "k-pop", "j-pop", "dance pop"],
            # Other genres
            "country": ["country", "country rock", "country pop", "bluegrass"],
            "jazz": ["jazz", "smooth jazz", "bebop", "swing"],
            "classical": ["classical", "orchestra", "symphony", "piano", "violin"],
            "blues": ["blues", "rhythm and blues", "r&b", "soul"],
            "reggae": ["reggae", "dancehall", "ska", "dub"],
            "folk": ["folk", "singer-songwriter", "acoustic", "indie folk"],
            "world": ["world", "latin", "afrobeat", "bossa nova", "samba"]
        }
        
        # Flatten genre list for search
        self.all_genre_terms = []
        for main_genre, subgenres in self.genre_map.items():
            self.all_genre_terms.append(main_genre)
            self.all_genre_terms.extend(subgenres)
        
        # Mood classifications
        self.mood_map = {
            "energetic": ["energetic", "upbeat", "party", "dance", "hype", "workout", "energy", "powerful"],
            "relaxing": ["relaxing", "chill", "calm", "peaceful", "ambient", "sleep", "meditation", "relax"],
            "happy": ["happy", "cheerful", "uplifting", "positive", "fun", "joy", "bright", "feel good"],
            "sad": ["sad", "melancholic", "emotional", "heartbreak", "sorrow", "tear", "cry", "depression"],
            "romantic": ["romantic", "love", "passionate", "sensual", "intimate", "valentine", "romance"],
            "dark": ["dark", "intense", "aggressive", "angry", "rage", "fury", "heavy"],
            "focus": ["focus", "concentration", "study", "work", "productivity", "background"],
        }
        
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

        # Patterns for featuring artists
        self.featuring_patterns = [
            r'feat\.?\s+([^,\(\)\[\]]+)',
            r'ft\.?\s+([^,\(\)\[\]]+)',
            r'featuring\s+([^,\(\)\[\]]+)',
            r'with\s+([^,\(\)\[\]]+)'
        ]
        
        # Cache for parsed title info to improve performance
        self.title_info_cache = {}
    
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
    
    def calculate_similarity(self, title1: str, title2: str, consider_genre: bool = True) -> float:
        """
        Calculate similarity between two titles with improved duplicate detection.
        
        Args:
            title1: First title
            title2: Second title
            consider_genre: Whether to consider genre when calculating similarity
                
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not title1 or not title2:
            return 0.0
                
        # Get core titles
        core_title1 = self.extract_core_title(title1)
        core_title2 = self.extract_core_title(title2)
        
        # Direct match on core title
        if core_title1 == core_title2:
            return 1.0
        
        # Parse title information
        info1 = self.parse_title_info(title1)
        info2 = self.parse_title_info(title2)
        
        # Calculate similarity based on parts
        similarity_score = 0.0
        
        # Artist similarity (45% weight - increased from 40%)
        if info1['artist'] and info2['artist']:
            artist_similarity = difflib.SequenceMatcher(None, info1['artist'].lower(), info2['artist'].lower()).ratio()
            
            # To avoid loops, we penalize exact song title matches from different artists
            if (info1['song_title'] and info2['song_title'] and 
                info1['song_title'].lower() == info2['song_title'].lower() and
                artist_similarity < 0.7):
                # If exact song title match but different artists, reduce similarity
                similarity_score += 0.45 * artist_similarity * 0.5  # Apply 50% penalty
            else:
                similarity_score += 0.45 * artist_similarity
        
        # Song title similarity (35% weight - decreased from 40%)
        if info1['song_title'] and info2['song_title']:
            song_similarity = difflib.SequenceMatcher(None, info1['song_title'].lower(), info2['song_title'].lower()).ratio()
            similarity_score += 0.35 * song_similarity
        
        # Genre similarity (20% weight if enabled)
        if consider_genre and info1['genres'] and info2['genres']:
            # Check for any common genres
            common_genres = set(info1['genres']).intersection(set(info2['genres']))
            if common_genres:
                similarity_score += 0.2
        
        # Check for recent playback tracking - prevent returning to a recently played song
        # This logic would need to be implemented separately, but adding a flag to indicate
        fingerprint1 = self.get_song_fingerprint(title1)
        fingerprint2 = self.get_song_fingerprint(title2)
        
        # If they generate the same fingerprint but we know they're different songs,
        # reduce the similarity to avoid loops
        if fingerprint1 == fingerprint2 and info1['artist'] and info2['artist'] and info1['artist'] != info2['artist']:
            similarity_score *= 0.5  # 50% penalty for likely duplicates
        
        # If we couldn't extract structured info, fall back to overall similarity
        if similarity_score == 0.0:
            overall_similarity = difflib.SequenceMatcher(None, core_title1, core_title2).ratio()
            return overall_similarity
        
        return min(1.0, similarity_score)
    
    def parse_title_info(self, title: str) -> Dict[str, Any]:
        """
        Parse a title string to extract artist, song title, genre, and mood.
        
        Returns:
            Dict with keys: artist, song_title, genres, moods, featuring_artists
        """
        # Check cache first
        if title in self.title_info_cache:
            return self.title_info_cache[title]
        
        # Initialize result
        result = {
            'artist': None,
            'song_title': None,
            'genres': [],
            'moods': [],
            'featuring_artists': []
        }
        
        # Early return for empty title
        if not title:
            return result
        
        # Extract artist
        result['artist'] = self.extract_artist(title)
        
        # Extract featured artists
        for pattern in self.featuring_patterns:
            matches = re.findall(pattern, title, re.IGNORECASE)
            for match in matches:
                if match and len(match) > 1:
                    result['featuring_artists'].append(match.strip())
        
        # Extract song title
        result['song_title'] = self.extract_song_title(title, result['artist'])
        
        # Extract genres
        result['genres'] = self.detect_genres(title)
        
        # Extract moods
        result['moods'] = self.detect_moods(title)
        
        # Cache result
        self.title_info_cache[title] = result
        
        return result
    
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
    
    def extract_song_title(self, title: str, artist: Optional[str] = None) -> Optional[str]:
        """
        Extract song title from a full title string.
        
        Args:
            title: Full title string
            artist: Artist name if already extracted
            
        Returns:
            Extracted song title or None if extraction failed
        """
        if not title:
            return None
            
        # Clean title first
        clean_title = self.extract_core_title(title)
        
        # If we have the artist, try to extract song part using it
        if artist:
            # Format: "Artist - Song"
            if " - " in title:
                parts = title.split(" - ", 1)
                if len(parts) > 1 and parts[0].strip().lower() == artist.lower():
                    return parts[1].strip()
            
            # Try to remove artist name from the beginning of the title
            artist_pattern = r'^\s*' + re.escape(artist.lower()) + r'(?:\s*[\-:]\s*|\s+)'
            match = re.search(artist_pattern, clean_title.lower())
            if match:
                song_title = clean_title[match.end():].strip()
                if song_title:
                    return song_title
        
        # Format: "Song (feat. Artist)"
        for pattern in self.featuring_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                # Get everything before the featuring part
                song_title = title[:match.start()].strip()
                if song_title:
                    return song_title
        
        # If we have "Artist - " format but couldn't extract before
        if " - " in title:
            song_title = title.split(" - ", 1)[1].strip()
            # Clean up the song title
            for extra in self.title_extra_identifiers:
                song_title = song_title.replace(extra, '').strip()
            return song_title
        
        # As a last resort, just return the cleaned title
        return clean_title
    
    def detect_genres(self, title: str) -> List[str]:
        """
        Detect music genres from title.
        
        Args:
            title: Title string to analyze
            
        Returns:
            List of detected genre names
        """
        if not title:
            return []
            
        detected_genres = []
        title_lower = title.lower()
        
        # Check for each genre term
        for genre_term in self.all_genre_terms:
            # Make sure we're matching whole words or phrases
            pattern = r'\b' + re.escape(genre_term) + r'\b'
            if re.search(pattern, title_lower):
                # Map back to main genre
                found_main_genre = False
                for main_genre, subgenres in self.genre_map.items():
                    if genre_term == main_genre or genre_term in subgenres:
                        if main_genre not in detected_genres:
                            detected_genres.append(main_genre)
                        found_main_genre = True
                        break
                
                # If not mapped to a main genre, add as is
                if not found_main_genre and genre_term not in detected_genres:
                    detected_genres.append(genre_term)
        
        return detected_genres
    
    def detect_moods(self, title: str) -> List[str]:
        """
        Detect moods from a title.
        
        Args:
            title: Title string to analyze
            
        Returns:
            List of detected mood names
        """
        if not title:
            return []
            
        detected_moods = []
        title_lower = title.lower()
        
        # Check against mood keywords
        for mood, keywords in self.mood_map.items():
            for keyword in keywords:
                if keyword in title_lower:
                    if mood not in detected_moods:
                        detected_moods.append(mood)
                    break
        
        return detected_moods
    
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
        
    def get_song_fingerprint(self, title: str) -> str:
        """
        Generate a simplified fingerprint for a song to help with duplicate detection.
        
        Args:
            title: Title of the song
            
        Returns:
            String fingerprint that can be compared
        """
        info = self.parse_title_info(title)
        
        # If we have artist and song, use them
        if info['artist'] and info['song_title']:
            artist = re.sub(r'[^\w]', '', info['artist'].lower())
            song = re.sub(r'[^\w]', '', info['song_title'].lower())
            return f"{artist}_{song}"
        
        # Otherwise use cleaned title
        clean = re.sub(r'[^\w]', '', self.extract_core_title(title))
        return clean