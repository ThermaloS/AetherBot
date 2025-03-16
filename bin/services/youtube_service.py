import asyncio
import functools
import logging
import yt_dlp
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger('discord_bot.youtube')

class YouTubeService:
    """Service for interacting with YouTube through yt_dlp."""
    
    def __init__(self, config=None):
        self.config = config
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
            
    async def search_similar_songs(self, title: str, artist: Optional[str] = None, 
                                   limit: int = 5, exclude_urls: List[str] = None) -> List[Dict[str, Any]]:
        """Search for songs similar to the given title/artist."""
        exclude_urls = exclude_urls or []
        
        # Create search query based on available info
        if artist:
            search_query = f"ytsearch{limit+5}:{artist} music -mix -compilation"
        else:
            search_query = f"ytsearch{limit+5}:{title} music similar -mix -compilation"
            
        logger.info(f"Searching for similar songs to: {title}")
        
        try:
            results = await self.extract_info_async(search_query)
            if not results or 'entries' not in results:
                return []
                
            filtered_results = []
            for entry in results['entries']:
                url = entry.get('webpage_url')
                if not url or url in exclude_urls:
                    continue
                    
                if len(filtered_results) >= limit:
                    break
                    
                filtered_results.append(entry)
                
            return filtered_results
        except Exception as e:
            logger.error(f"Error searching similar songs: {e}")
            return []