import discord
from discord.ext import commands
from discord import app_commands
from collections import deque

from bin.cogs.music_cog import MusicCog

class GeneralMusicControls(commands.Cog):
    def __init__(self, bot: commands.Bot, music_cog: 'MusicCog'):
        self.bot = bot
        self.music_cog = music_cog
        super().__init__()
        self.vote_messages = {}  # Store vote message IDs

    @app_commands.command(name="queue", description="Show the current song queue.")
    async def queue(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id not in self.music_cog.song_queues or not self.music_cog.song_queues[guild_id]:
            await interaction.response.send_message("The queue is empty.")
            return

        queue_list = "\n".join(
            f"{i+1}. {title}" for i, (query, title) in enumerate(self.music_cog.song_queues[guild_id])
        )
        await interaction.response.send_message(f"**Current Queue:**\n{queue_list}")

    @app_commands.command(name="pause", description="Pause the currently playing song.")
    async def pause(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            return await interaction.response.send_message("I'm not in a voice channel.")

        if not voice_client.is_playing():
            return await interaction.response.send_message("Nothing is currently playing.")

        voice_client.pause()
        await interaction.response.send_message("Playback paused!")

    @app_commands.command(name="resume", description="Resume the currently paused song.")
    async def resume(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            return await interaction.response.send_message("I'm not in a voice channel.")

        if not voice_client.is_paused():
            return await interaction.response.send_message("I'm not paused right now.")

        voice_client.resume()
        await interaction.response.send_message("Playback resumed!")

    @app_commands.command(name="voteskip", description="Vote to skip the current song.")
    async def voteskip(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        guild_id = str(interaction.guild_id)

        if voice_client is None or not voice_client.is_connected():
            return await interaction.response.send_message("I'm not in a voice channel.")

        if not voice_client.is_playing():
            return await interaction.response.send_message("Nothing is currently playing.")

        voice_channel = voice_client.channel
        required_votes = len(voice_channel.members) // 2 + 1  # Majority vote

        embed = discord.Embed(title="Vote Skip", description=f"Vote to skip the current song. {required_votes} votes needed.")
        view = VoteSkipView(self, guild_id, required_votes, voice_channel, voice_client, interaction.user.id) #pass the user ID
        await interaction.response.send_message(embed=embed, view=view)

class VoteSkipView(discord.ui.View):
    def __init__(self, cog: GeneralMusicControls, guild_id, required_votes, voice_channel, voice_client, initiating_user_id): #add initiating_user_id
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.required_votes = required_votes
        self.voice_channel = voice_channel
        self.voice_client = voice_client
        self.yes_votes = {initiating_user_id} #add the user ID to the set.
        self.no_votes = set()

    @discord.ui.button(label="YES", style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in self.yes_votes:
            await interaction.response.send_message("You've already voted YES.", ephemeral=True)
            return

        self.yes_votes.add(user_id)
        if user_id in self.no_votes:
            self.no_votes.remove(user_id)

        if len(self.yes_votes) >= self.required_votes:
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()
                await interaction.response.edit_message(content="Vote skip successful!", view=None)
            else:
                await interaction.response.edit_message(content="Skip failed, music stopped before vote was completed.", view=None)
            self.stop()
        else:
            await interaction.response.send_message(f"Vote added. {self.required_votes - len(self.yes_votes)} more YES votes needed.", ephemeral=True)

    @discord.ui.button(label="NO", style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in self.no_votes:
            await interaction.response.send_message("You've already voted NO.", ephemeral=True)
            return
        self.no_votes.add(user_id)
        if user_id in self.yes_votes:
            self.yes_votes.remove(user_id)
        await interaction.response.send_message("Vote added.", ephemeral=True)

async def setup(bot: commands.Bot, music_cog: 'MusicCog'):
    await bot.add_cog(GeneralMusicControls(bot, music_cog))
    print("General Music Commands Added")