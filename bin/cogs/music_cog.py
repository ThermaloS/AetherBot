import discord
from discord.ext import commands
from collections import deque
import yt_dlp
import asyncio
import functools

class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.song_queues = {}
        self.play_delay = 0
        self.volumes = {}
        super().__init__()

    async def search_ytdlp_async(self, query, ydl_opts):
        loop = asyncio.get_running_loop()
        func = functools.partial(self._extract, query, ydl_opts)
        return await loop.run_in_executor(None, func)

    def _extract(self, query, ydl_opts):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(query, download=False)
            return results

    async def play_next_song(self, guild_id, interaction):
        voice_client = interaction.guild.voice_client
        if voice_client is None:
            return

        if guild_id in self.song_queues and self.song_queues[guild_id]:
            original_query, title = self.song_queues[guild_id].popleft()

            ffmpeg_options = {
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                "options": "-vn",
            }

            async def try_play(url_to_try):
                try:
                    source = discord.FFmpegPCMAudio(url_to_try, **ffmpeg_options)
                    volume = self.volumes.get(guild_id, 0.05)
                    source = discord.PCMVolumeTransformer(source, volume=volume)

                    def after_play(error):
                        if error:
                            print(f"Playback error: {error}")
                        if not self.song_queues[guild_id]:
                            async def add_similar_songs():
                                try:
                                    similar_songs = await self.find_similar_songs(original_query)
                                    if similar_songs:
                                        self.song_queues[guild_id].extend(similar_songs)
                                        # Use interaction.channel.send directly, as interaction might be invalid
                                        channel = self.bot.get_guild(int(guild_id)).get_channel(interaction.channel_id)
                                        await channel.send("Adding similar songs to the queue...")
                                except Exception as e:
                                    print(f"Error finding similar songs: {e}")

                            asyncio.run_coroutine_threadsafe(add_similar_songs(), self.bot.loop)
                        if self.song_queues[guild_id] or voice_client.is_playing():
                            asyncio.run_coroutine_threadsafe(self.play_next_song(guild_id, interaction), self.bot.loop)
                        elif voice_client.is_connected():
                            asyncio.run_coroutine_threadsafe(voice_client.disconnect(), self.bot.loop)
                            asyncio.run_coroutine_threadsafe(interaction.channel.send("Queue finished, disconnecting."), self.bot.loop)

                    voice_client.play(source, after=after_play)
                    await interaction.channel.send(f"Now playing: **{title}** (Volume: {int(volume * 100)}%)")
                    return True

                except discord.ClientException as e:
                    print(f"FFmpeg error: {e}")
                    return False
                except Exception as e:
                    print(f"An unexpected error occurred: {e}")
                    return False

            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'default_search': 'ytsearch',
            }
            try:
                initial_results = await self.search_ytdlp_async(original_query, ydl_opts)
                if 'entries' in initial_results:
                    initial_url = initial_results['entries'][0]['url']
                elif 'url' in initial_results:
                    initial_url = initial_results['url']
                else:
                    await interaction.channel.send("Failed to find a playable URL.")
                    asyncio.run_coroutine_threadsafe(self.play_next_song(guild_id, interaction), self.bot.loop)
                    return

                if not await try_play(initial_url):
                    await interaction.channel.send("Failed to play the song.")
                    asyncio.run_coroutine_threadsafe(self.play_next_song(guild_id, interaction), self.bot.loop)

            except Exception as e:
                print(f"Extraction error: {e}")
                await interaction.channel.send("An error occurred during extraction.")
                asyncio.run_coroutine_threadsafe(self.play_next_song(guild_id, interaction), self.bot.loop)

        elif voice_client.is_connected():
            asyncio.run_coroutine_threadsafe(voice_client.disconnect(), self.bot.loop)
            asyncio.run_coroutine_threadsafe(interaction.channel.send("Queue finished, disconnecting."), self.bot.loop)

    async def find_similar_songs(self, original_query):
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'default_search': 'ytsearch',
            'extract_flat': 'in_playlist'
        }
        try:
            results = await self.search_ytdlp_async(original_query, ydl_opts)
            if 'entries' in results:
                results = results['entries'][0]
            if 'related_videos' in results:
                similar_songs = deque()
                for related_video in results['related_videos'][:3]:
                    similar_songs.append((related_video['webpage_url'], related_video['title']))
                return similar_songs
            else:
                return None
        except Exception as e:
            print(f"Error finding similar songs: {e}")
            return None

async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
    print("MusicCog loaded!")