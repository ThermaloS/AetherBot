import discord
from discord.ext import commands
from discord import app_commands
import logging
from collections import deque
from typing import Set, Optional

# Local imports
from bin.cogs.music.music_cog import MusicCog

logger = logging.getLogger('discord_bot.music.general')

class GeneralMusicControls(commands.Cog):
    """Provides general music controls available to all users."""
    
    def __init__(self, bot: commands.Bot, music_cog: MusicCog):
        """
        Initialize general music controls.
        
        Args:
            bot: The Discord bot instance
            music_cog: The main MusicCog instance for music playback
        """
        self.bot = bot
        self.music_cog = music_cog
        super().__init__()
        self.vote_messages = {}  # Store vote message IDs
        logger.info("GeneralMusicControls loaded")

    @app_commands.command(name="queue", description="Show the current song queue.")
    async def queue(self, interaction: discord.Interaction):
        """Display the current song queue."""
        guild_id = str(interaction.guild_id)
        
        if not interaction.guild.voice_client:
            await interaction.response.send_message("I'm not connected to any voice channel.")
            return
            
        if guild_id not in self.music_cog.song_queues or not self.music_cog.song_queues[guild_id]:
            await interaction.response.send_message("The queue is empty.")
            return

        # Create a more visually appealing embed for the queue
        embed = discord.Embed(
            title="Current Music Queue",
            description=f"Total songs in queue: {len(self.music_cog.song_queues[guild_id])}",
            color=discord.Color.blue()
        )
        
        # Add current song if playing
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            current_song = self.music_cog.get_last_played(guild_id)
            if current_song:
                embed.add_field(
                    name="🎵 Now Playing",
                    value=f"**{current_song[1]}**",
                    inline=False
                )
        
        # Add queued songs
        queue_text = ""
        for i, (_, title) in enumerate(self.music_cog.song_queues[guild_id]):
            if i < 10:  # Show first 10 songs
                queue_text += f"{i+1}. {title}\n"
            else:
                remaining = len(self.music_cog.song_queues[guild_id]) - 10
                queue_text += f"*...and {remaining} more songs*"
                break
                
        if queue_text:
            embed.add_field(
                name="Up Next",
                value=queue_text,
                inline=False
            )
            
        # Add footer with current volume
        volume = int(self.music_cog.get_guild_volume(guild_id) * 100)
        embed.set_footer(text=f"Current Volume: {volume}%")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pause", description="Pause the currently playing song.")
    async def pause(self, interaction: discord.Interaction):
        """Pause the current song playback."""
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            return await interaction.response.send_message("I'm not in a voice channel.")

        if not voice_client.is_playing():
            return await interaction.response.send_message("Nothing is currently playing.")

        if voice_client.is_paused():
            return await interaction.response.send_message("Playback is already paused.")

        voice_client.pause()
        await interaction.response.send_message("⏸️ Playback paused!")

    @app_commands.command(name="resume", description="Resume the currently paused song.")
    async def resume(self, interaction: discord.Interaction):
        """Resume playback of a paused song."""
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            return await interaction.response.send_message("I'm not in a voice channel.")

        if not voice_client.is_paused():
            return await interaction.response.send_message("I'm not paused right now.")

        voice_client.resume()
        await interaction.response.send_message("▶️ Playback resumed!")

    @app_commands.command(name="voteskip", description="Vote to skip the current song.")
    async def voteskip(self, interaction: discord.Interaction):
        """Initiate a vote to skip the current song."""
        voice_client = interaction.guild.voice_client
        guild_id = str(interaction.guild_id)

        if voice_client is None or not voice_client.is_connected():
            return await interaction.response.send_message("I'm not in a voice channel.")

        if not voice_client.is_playing():
            return await interaction.response.send_message("Nothing is currently playing.")

        # Get members in the voice channel
        voice_channel = voice_client.channel
        members_in_channel = [m for m in voice_channel.members if not m.bot]
        
        # If only one person or empty, skip immediately
        if len(members_in_channel) <= 1:
            voice_client.stop()
            return await interaction.response.send_message("⏭️ Skipped the current song.")
            
        # Calculate required votes - majority of users
        required_votes = len(members_in_channel) // 2 + 1

        embed = discord.Embed(
            title="Vote Skip",
            description=f"Vote to skip the current song.\n{required_votes} votes needed.",
            color=discord.Color.gold()
        )
        
        # Extract currently playing song
        current_song = self.music_cog.get_last_played(guild_id)
        if current_song:
            embed.add_field(name="Currently Playing", value=current_song[1], inline=False)
            
        embed.set_footer(text=f"Started by {interaction.user.display_name}")
        
        view = VoteSkipView(
            self, 
            guild_id, 
            required_votes, 
            voice_channel, 
            voice_client, 
            interaction.user.id
        )
        
        await interaction.response.send_message(embed=embed, view=view)

class VoteSkipView(discord.ui.View):
    """View for handling vote skip functionality."""
    
    def __init__(
        self, 
        cog: GeneralMusicControls, 
        guild_id: str, 
        required_votes: int, 
        voice_channel: discord.VoiceChannel, 
        voice_client: discord.VoiceClient, 
        initiating_user_id: int
    ):
        """Initialize the vote skip view."""
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.required_votes = required_votes
        self.voice_channel = voice_channel
        self.voice_client = voice_client
        self.yes_votes: Set[int] = {initiating_user_id}  # Add the user ID to the set
        self.no_votes: Set[int] = set()
        self.voters_in_channel: Set[int] = {m.id for m in voice_channel.members if not m.bot}

    @discord.ui.button(label="YES", style=discord.ButtonStyle.green, emoji="👍")
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle YES vote button press."""
        user_id = interaction.user.id
        
        # Check if user is in the voice channel
        if user_id not in self.voters_in_channel:
            await interaction.response.send_message(
                "You need to be in the voice channel to vote!", 
                ephemeral=True
            )
            return
            
        if user_id in self.yes_votes:
            await interaction.response.send_message("You've already voted YES.", ephemeral=True)
            return

        self.yes_votes.add(user_id)
        if user_id in self.no_votes:
            self.no_votes.remove(user_id)

        if len(self.yes_votes) >= self.required_votes:
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()
                await interaction.response.edit_message(
                    content="⏭️ Vote skip successful! Skipping to the next song.",
                    embed=None,
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content="Skip failed, music stopped before vote was completed.",
                    embed=None,
                    view=None
                )
            self.stop()
        else:
            votes_needed = self.required_votes - len(self.yes_votes)
            await interaction.response.send_message(
                f"Vote added. {votes_needed} more YES vote{'s' if votes_needed != 1 else ''} needed.",
                ephemeral=True
            )
            
            # Update the message to show current vote count
            embed = interaction.message.embeds[0]
            embed.description = f"Vote to skip the current song.\n{len(self.yes_votes)}/{self.required_votes} votes (need {votes_needed} more)"
            await interaction.message.edit(embed=embed)

    @discord.ui.button(label="NO", style=discord.ButtonStyle.red, emoji="👎")
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle NO vote button press."""
        user_id = interaction.user.id
        
        # Check if user is in the voice channel
        if user_id not in self.voters_in_channel:
            await interaction.response.send_message(
                "You need to be in the voice channel to vote!", 
                ephemeral=True
            )
            return
            
        if user_id in self.no_votes:
            await interaction.response.send_message("You've already voted NO.", ephemeral=True)
            return
            
        self.no_votes.add(user_id)
        if user_id in self.yes_votes:
            self.yes_votes.remove(user_id)
            
        votes_needed = self.required_votes - len(self.yes_votes)
        await interaction.response.send_message("Vote added.", ephemeral=True)
        
        # Update the message to show current vote count
        embed = interaction.message.embeds[0]
        embed.description = f"Vote to skip the current song.\n{len(self.yes_votes)}/{self.required_votes} votes (need {votes_needed} more)"
        await interaction.message.edit(embed=embed)

    async def on_timeout(self):
        """Handle view timeout."""
        # Get the message this view is attached to
        for item in self.children:
            item.disabled = True
            
        # Try to edit the message if it still exists
        try:
            message = await self.message.edit(
                content="Vote skip timed out.",
                view=self
            )
        except Exception:
            pass

async def setup(bot: commands.Bot, music_cog: Optional[MusicCog] = None):
    """
    Setup function to register the cog with the bot.
    
    Args:
        bot: The Discord bot instance
        music_cog: The MusicCog instance
    """
    if music_cog is None:
        # Try to get the music cog if it wasn't passed
        music_cog = bot.get_cog("MusicCog")
        if music_cog is None:
            logger.error("MusicCog not found. Cannot load GeneralMusicControls.")
            return None
            
    cog = GeneralMusicControls(bot, music_cog)
    await bot.add_cog(cog)
    logger.info("General Music Commands Added")
    return cog