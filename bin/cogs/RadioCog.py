import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import functools
from typing import Dict, List, Tuple, Any, Optional

from bin.cogs.music_cog import MusicCog

class RadioCog(commands.Cog):
    """A Discord bot cog for radio-like features that automatically queue similar songs."""
    
    def __init__(self, bot: commands.Bot, music_cog: MusicCog):
        self.bot = bot
        self.music_cog = music_cog  # Store reference to the music cog
        self.radio_mode: Dict[int, bool] = {}  # {guild_id: is_radio_enabled}
        super().__init__()
    
    async def extract_info_async(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts video information asynchronously using yt_dlp."""
        loop = asyncio.get_running_loop()
        func = functools.partial(self._extract, query, ydl_opts)
        return await loop.run_in_executor(None, func)
    
    def _extract(self, query: str, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        """Helper method to extract info with yt_dlp."""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(query, download=False)
            return results
    
    async def find_similar_songs(self, query: str, limit: int = 3) -> List[Tuple[str, str]]:
        """Finds similar songs based on the original query."""
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'default_search': 'ytsearch',
            'extract_flat': 'in_playlist'
        }
        
        try:
            results = await self.extract_info_async(query, ydl_opts)
            
            # Handle search vs direct URL results
            if 'entries' in results:
                results = results['entries'][0]
                
            # Find related videos
            similar_songs = []
            if 'related_videos' in results:
                for related in results['related_videos'][:limit]:
                    similar_songs.append((related['webpage_url'], related['title']))
                    
            return similar_songs
        except Exception as e:
            print(f"Error finding similar songs: {e}")
            return []

    def is_radio_enabled(self, guild_id: int) -> bool:
        """Checks if radio mode is enabled for a guild."""
        return self.radio_mode.get(guild_id, False)
    
    @app_commands.command(name="radio", description="Toggle radio mode on/off.")
    async def toggle_radio(self, ctx: commands.Context) -> None:
        """Toggles radio mode on/off."""
        guild_id = ctx.guild.id
        current_state = self.is_radio_enabled(guild_id)
        new_state = not current_state
        self.radio_mode[guild_id] = new_state
        
        await ctx.send(f"Radio mode is now {'enabled' if new_state else 'disabled'}")
    
    async def add_similar_songs_to_queue(self, query: str, channel: discord.TextChannel) -> List[Tuple[str, str]]:
        """Find similar songs based on the query."""
        try:
            await channel.send("Radio mode: Looking for similar songs...")
            similar_songs = await self.find_similar_songs(query)
            if not similar_songs:
                await channel.send("Couldn't find any similar songs.")
                return []
                
            await channel.send(f"Found {len(similar_songs)} similar songs.")
            return similar_songs
        except Exception as e:
            print(f"Error adding similar songs: {e}")
            await channel.send(f"Error finding similar songs: {e}")
            return []


async def setup(bot: commands.Bot, music_cog: MusicCog):
    await bot.add_cog(RadioCog(bot, music_cog))
    print("RadioCog loaded!")