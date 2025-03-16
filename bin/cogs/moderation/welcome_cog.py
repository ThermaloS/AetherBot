import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import logging
from typing import Optional, Dict, Any, Union

logger = logging.getLogger('discord_bot.welcome')

class Welcome(commands.Cog):
    """Cog for handling welcome messages and role assignment for new members."""
    
    def __init__(self, bot: commands.Bot, config=None):
        """
        Initialize the welcome cog.
        
        Args:
            bot: The Discord bot instance
            config: Optional configuration object
        """
        self.bot = bot
        self.config = config
        
        # Default welcome settings
        self.default_welcome_message = "Welcome to {server_name}, {member_mention}!"
        self.default_welcome_title = "Welcome to {server_name}!"
        self.default_welcome_description = "We're glad to have you here, {member_mention}!"
        self.default_welcome_color = 0x2ECC71  # Green
        
        # Initialize configuration
        self.server_config_file = "server_config.json"
        self.server_config: Dict[str, Any] = {}
        self.load_config()
        logger.info("Welcome cog initialized")

    def load_config(self):
        """Load server configuration from file."""
        try:
            if not os.path.exists(self.server_config_file):
                self.server_config = {}
                self.save_config()
                return
                
            with open(self.server_config_file, "r") as f:
                file_content = f.read().strip()
                if file_content:  # Check if the file has content
                    self.server_config = json.loads(file_content)
                else:
                    # Handle empty file case
                    self.server_config = {}
                    self.save_config()  # Initialize with empty object
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in {self.server_config_file}. Creating new config.")
            self.server_config = {}
            self.save_config()
        except Exception as e:
            logger.error(f"Error loading welcome config: {e}")
            self.server_config = {}

    def save_config(self):
        """Save server configuration to file."""
        try:
            with open(self.server_config_file, "w") as f:
                json.dump(self.server_config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving welcome config: {e}")

    async def check_permissions(self, interaction: discord.Interaction):
        """
        Check if the user has appropriate permissions for welcome commands.
        
        Args:
            interaction: Discord interaction
            
        Returns:
            True if user has required permissions, False otherwise
        """
        # Allow administrators to bypass specific permission checks
        if interaction.user.guild_permissions.administrator:
            return True
            
        if interaction.user.guild_permissions.manage_channels and interaction.user.guild_permissions.manage_roles:
            return True
        else:
            await interaction.response.send_message(
                "You need both 'Manage Channels' and 'Manage Roles' permissions to use this command.", 
                ephemeral=True
            )
            return False

    @app_commands.command(name="setwelcomechannel", description="Sets the welcome channel for this server.")
    async def setwelcomechannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Set the channel for welcome messages.
        
        Args:
            interaction: Discord interaction
            channel: The channel to send welcome messages to
        """
        if not await self.check_permissions(interaction):
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.server_config:
            self.server_config[guild_id] = {}
            
        # Store channel ID instead of name for reliability
        self.server_config[guild_id]["welcome_channel_id"] = channel.id
        # Keep name for backward compatibility and readability in the config file
        self.server_config[guild_id]["welcome_channel_name"] = channel.name
        
        self.save_config()
        
        embed = discord.Embed(
            title="Welcome Channel Set",
            description=f"Welcome messages will now be sent to {channel.mention}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="setwelcomerole", description="Sets the welcome role for this server.")
    async def setwelcomerole(self, interaction: discord.Interaction, role: discord.Role):
        """
        Set the role to give to new members.
        
        Args:
            interaction: Discord interaction
            role: The role to assign to new members
        """
        if not await self.check_permissions(interaction):
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.server_config:
            self.server_config[guild_id] = {}
            
        # Store role ID instead of name for reliability
        self.server_config[guild_id]["welcome_role_id"] = role.id
        # Keep name for backward compatibility and readability in the config file
        self.server_config[guild_id]["welcome_role_name"] = role.name
        
        self.save_config()
        
        embed = discord.Embed(
            title="Welcome Role Set",
            description=f"New members will now receive the **{role.name}** role",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="setwelcomemessage", 
        description="Sets a custom welcome message for this server."
    )
    @app_commands.describe(
        message="Custom message for welcoming new members (use {member_mention} and {server_name} as placeholders)"
    )
    async def setwelcomemessage(self, interaction: discord.Interaction, message: str):
        """
        Set a custom welcome message.
        
        Args:
            interaction: Discord interaction
            message: Custom welcome message with placeholders
        """
        if not await self.check_permissions(interaction):
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.server_config:
            self.server_config[guild_id] = {}
            
        # Store the custom message
        self.server_config[guild_id]["welcome_message"] = message
        self.save_config()
        
        # Preview the message
        preview = message.replace(
            "{member_mention}", interaction.user.mention
        ).replace(
            "{server_name}", interaction.guild.name
        )
        
        embed = discord.Embed(
            title="Welcome Message Set",
            description="Your custom welcome message has been set.",
            color=discord.Color.green()
        )
        embed.add_field(name="Preview", value=preview, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="welcomesettings", 
        description="View current welcome settings for this server."
    )
    async def welcomesettings(self, interaction: discord.Interaction):
        """
        Display current welcome settings.
        
        Args:
            interaction: Discord interaction
        """
        guild_id = str(interaction.guild.id)
        config = self.server_config.get(guild_id, {})
        
        if not config:
            await interaction.response.send_message(
                "No welcome settings have been configured for this server.", 
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title=f"Welcome Settings for {interaction.guild.name}",
            color=discord.Color.blue()
        )
        
        # Welcome Channel
        channel_id = config.get("welcome_channel_id")
        channel_name = config.get("welcome_channel_name", "Not set")
        
        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            if channel:
                embed.add_field(
                    name="Welcome Channel", 
                    value=f"{channel.mention} (`{channel.name}`)", 
                    inline=False
                )
            else:
                embed.add_field(
                    name="Welcome Channel", 
                    value=f"⚠️ Channel not found: `{channel_name}` (ID: {channel_id})", 
                    inline=False
                )
        else:
            embed.add_field(name="Welcome Channel", value="Not set", inline=False)
            
        # Welcome Role
        role_id = config.get("welcome_role_id")
        role_name = config.get("welcome_role_name", "Not set")
        
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                embed.add_field(
                    name="Welcome Role", 
                    value=f"`{role.name}`", 
                    inline=False
                )
            else:
                embed.add_field(
                    name="Welcome Role", 
                    value=f"⚠️ Role not found: `{role_name}` (ID: {role_id})", 
                    inline=False
                )
        else:
            embed.add_field(name="Welcome Role", value="Not set", inline=False)
            
        # Welcome Message
        welcome_message = config.get("welcome_message", self.default_welcome_message)
        
        # Preview the message
        preview = welcome_message.replace(
            "{member_mention}", interaction.user.mention
        ).replace(
            "{server_name}", interaction.guild.name
        )
        
        embed.add_field(name="Welcome Message", value=preview, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="testwelcome", 
        description="Test the welcome message for this server."
    )
    async def testwelcome(self, interaction: discord.Interaction):
        """
        Test the welcome message.
        
        Args:
            interaction: Discord interaction
        """
        if not await self.check_permissions(interaction):
            return
            
        await interaction.response.defer(ephemeral=True)
        
        guild_id = str(interaction.guild.id)
        config = self.server_config.get(guild_id, {})
        
        if not config:
            await interaction.followup.send(
                "No welcome settings have been configured for this server."
            )
            return
            
        # Create a simulated welcome message for the requesting user
        await self._send_welcome_message(
            interaction.user, 
            interaction.guild, 
            is_test=True
        )
        
        await interaction.followup.send(
            "Welcome message test sent. Check the welcome channel to see the result."
        )

    async def _send_welcome_message(self, member: discord.Member, guild: discord.Guild, is_test: bool = False):
        """
        Send a welcome message for a new member.
        
        Args:
            member: The Discord member to welcome
            guild: The guild (server) the member joined
            is_test: Whether this is a test message
        """
        guild_id = str(guild.id)
        config = self.server_config.get(guild_id, {})
        
        if not config:
            logger.warning(f"No welcome config for guild {guild.name} ({guild.id})")
            return
            
        # Get channel (by ID first, then by name as fallback)
        welcome_channel = None
        channel_id = config.get("welcome_channel_id")
        channel_name = config.get("welcome_channel_name")
        
        if channel_id:
            welcome_channel = guild.get_channel(channel_id)
            
        if welcome_channel is None and channel_name:
            welcome_channel = discord.utils.get(guild.text_channels, name=channel_name)
            
        if welcome_channel is None:
            logger.warning(f"Welcome channel not found for guild {guild.name} ({guild.id})")
            return
            
        # Get welcome message
        welcome_message = config.get("welcome_message", self.default_welcome_message)
        welcome_message = welcome_message.replace(
            "{member_mention}", member.mention
        ).replace(
            "{server_name}", guild.name
        )
        
        # Add test indicator if this is a test
        if is_test:
            welcome_message = f"**[TEST]** {welcome_message}"
            
        # Create embed
        embed_title = self.default_welcome_title.replace(
            "{server_name}", guild.name
        )
        
        embed_description = self.default_welcome_description.replace(
            "{member_mention}", member.mention
        )
        
        embed = discord.Embed(
            title=embed_title,
            description=embed_description,
            color=discord.Color.green()
        )
        
        # Set user avatar
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        else:
            default_avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
            embed.set_thumbnail(url=default_avatar_url)
            
        # Add member info
        embed.add_field(
            name="Member", 
            value=f"{member.name}#{member.discriminator if hasattr(member, 'discriminator') else '0'}", 
            inline=True
        )
        
        embed.add_field(
            name="Account Created", 
            value=f"<t:{int(member.created_at.timestamp())}:R>", 
            inline=True
        )
        
        # Add server member count
        embed.add_field(
            name="Member Count", 
            value=f"{guild.member_count} members", 
            inline=True
        )
        
        # Send the message
        try:
            logger.info(f"Sending welcome message for {member.name} in {guild.name}")
            await welcome_channel.send(welcome_message, embed=embed)
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Handle new member joining.
        
        Args:
            member: The member who joined
        """
        guild = member.guild
        guild_id = str(guild.id)
        config = self.server_config.get(guild_id, {})

        if not config:
            logger.debug(f"No welcome config for guild {guild.name} ({guild.id})")
            return

        # Send welcome message
        await self._send_welcome_message(member, guild)

        # Assign role (if configured)
        role = None
        role_id = config.get("welcome_role_id")
        role_name = config.get("welcome_role_name")
        
        if role_id:
            role = guild.get_role(role_id)
            
        if role is None and role_name:
            role = discord.utils.get(guild.roles, name=role_name)
            
        if role:
            try:
                logger.info(f"Assigning role {role.name} to {member.name} in {guild.name}")
                await member.add_roles(role)
            except discord.Forbidden:
                logger.error(f"Cannot assign role {role.name} - missing permissions")
                
                # Try to notify in welcome channel
                welcome_channel = None
                channel_id = config.get("welcome_channel_id")
                
                if channel_id:
                    welcome_channel = guild.get_channel(channel_id)
                    
                if welcome_channel:
                    await welcome_channel.send(
                        f"⚠️ Could not give {member.mention} the {role.name} role. Bot lacks permissions."
                    )
            except discord.HTTPException as e:
                logger.error(f"Failed to assign role {role.name}: {e}")
                
                # Try to notify in welcome channel
                welcome_channel = None
                channel_id = config.get("welcome_channel_id")
                
                if channel_id:
                    welcome_channel = guild.get_channel(channel_id)
                    
                if welcome_channel:
                    await welcome_channel.send(
                        f"⚠️ Failed to give {member.mention} the {role.name} role. An unexpected error occurred."
                    )

async def setup(bot: commands.Bot, config=None):
    """
    Setup function to register the cog with the bot.
    
    Args:
        bot: The Discord bot instance
        config: Optional configuration object
    """
    cog = Welcome(bot, config)
    await bot.add_cog(cog)
    logger.info("Welcome Cog loaded!")
    return cog