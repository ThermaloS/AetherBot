import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import logging
import asyncio
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
                logger.info(f"No config file found. Creating new one at {self.server_config_file}")
                self.server_config = {}
                self.save_config()
                return
                
            with open(self.server_config_file, "r") as f:
                file_content = f.read().strip()
                if file_content:  # Check if the file has content
                    self.server_config = json.loads(file_content)
                    logger.info(f"Loaded config with {len(self.server_config)} server(s)")
                else:
                    # Handle empty file case
                    logger.warning(f"Config file {self.server_config_file} is empty")
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
            logger.info(f"Saved configuration to {self.server_config_file}")
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
        try:
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
        except Exception as e:
            logger.error(f"Error checking permissions: {e}")
            await interaction.response.send_message(
                "An error occurred while checking permissions. Please try again later.",
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
        try:
            logger.info(f"setwelcomechannel called by {interaction.user} for channel {channel.name}")
            
            if not await self.check_permissions(interaction):
                return

            # Verify bot has permissions to send messages in the channel
            bot_permissions = channel.permissions_for(interaction.guild.me)
            if not bot_permissions.send_messages or not bot_permissions.embed_links:
                await interaction.response.send_message(
                    f"I don't have permission to send messages or embeds in {channel.mention}. "
                    f"Please grant me the 'Send Messages' and 'Embed Links' permissions in that channel.",
                    ephemeral=True
                )
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
            logger.info(f"Set welcome channel to {channel.name} (ID: {channel.id}) for guild {interaction.guild.name}")
            
        except Exception as e:
            logger.error(f"Error in setwelcomechannel: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

    @app_commands.command(name="setwelcomerole", description="Sets the welcome role for this server.")
    async def setwelcomerole(self, interaction: discord.Interaction, role: discord.Role):
        """
        Set the role to give to new members.
        
        Args:
            interaction: Discord interaction
            role: The role to assign to new members
        """
        try:
            logger.info(f"setwelcomerole called by {interaction.user} for role {role.name}")
            
            if not await self.check_permissions(interaction):
                return

            # Check if bot can manage roles and has a higher position than the role
            bot_member = interaction.guild.me
            if not bot_member.guild_permissions.manage_roles:
                await interaction.response.send_message(
                    "I don't have the 'Manage Roles' permission, which is required to assign roles to new members.",
                    ephemeral=True
                )
                return
                
            if bot_member.top_role <= role:
                await interaction.response.send_message(
                    f"I cannot assign the {role.name} role as it is higher than or equal to my highest role. "
                    f"Please move my role above this role in the server settings.",
                    ephemeral=True
                )
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
            logger.info(f"Set welcome role to {role.name} (ID: {role.id}) for guild {interaction.guild.name}")
            
        except Exception as e:
            logger.error(f"Error in setwelcomerole: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

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
        try:
            logger.info(f"setwelcomemessage called by {interaction.user}")
            
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
            logger.info(f"Set welcome message for guild {interaction.guild.name}")
            
        except Exception as e:
            logger.error(f"Error in setwelcomemessage: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred: {e}",
                ephemeral=True
            )

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
        try:
            logger.info(f"welcomesettings called by {interaction.user}")
            
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
            
        except Exception as e:
            logger.error(f"Error in welcomesettings: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred while retrieving welcome settings: {e}",
                ephemeral=True
            )

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
        try:
            logger.info(f"testwelcome called by {interaction.user}")
            
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
            
            # Get channel info for feedback
            channel_id = config.get("welcome_channel_id")
            channel_name = config.get("welcome_channel_name", "Not set")
            
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                channel_info = f"<#{channel_id}>" if channel else f"Channel ID: {channel_id} (not found)"
            else:
                channel_info = f"Channel name: {channel_name} (not configured properly)"
                
            # Tell the user where to look for the message
            await interaction.followup.send(
                f"Attempting to send a test welcome message to {channel_info}..."
            )
            
            # Send the test welcome message with a timeout
            try:
                success = await asyncio.wait_for(
                    self._send_welcome_message(
                        interaction.user, 
                        interaction.guild, 
                        is_test=True
                    ),
                    timeout=10.0  # 10 second timeout
                )
                
                if success:
                    await interaction.followup.send(
                        "Welcome message test sent successfully. Check the welcome channel to see the result."
                    )
                else:
                    await interaction.followup.send(
                        "Failed to send the test welcome message. Please check the bot's permissions and channel configuration."
                    )
            except asyncio.TimeoutError:
                logger.error("Timed out sending test welcome message")
                await interaction.followup.send(
                    "The operation timed out. This could indicate a permissions issue or network problem."
                )
                
        except Exception as e:
            logger.error(f"Error in testwelcome: {e}", exc_info=True)
            await interaction.followup.send(
                f"An error occurred while testing the welcome message: {e}"
            )

    async def _send_welcome_message(self, member: discord.Member, guild: discord.Guild, is_test: bool = False):
        """
        Send a welcome message for a new member.
        
        Args:
            member: The Discord member to welcome
            guild: The guild (server) the member joined
            is_test: Whether this is a test message
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        try:
            logger.info(f"Sending welcome message for {member.name} in {guild.name} (Test: {is_test})")
            
            guild_id = str(guild.id)
            config = self.server_config.get(guild_id, {})
            
            if not config:
                logger.warning(f"No welcome config for guild {guild.name} ({guild.id})")
                return False
                
            # Get channel (by ID first, then by name as fallback)
            welcome_channel = None
            channel_id = config.get("welcome_channel_id")
            channel_name = config.get("welcome_channel_name")
            
            if channel_id:
                welcome_channel = guild.get_channel(channel_id)
                logger.debug(f"Looking up channel by ID {channel_id}: {welcome_channel}")
            
            if welcome_channel is None and channel_name:
                welcome_channel = discord.utils.get(guild.text_channels, name=channel_name)
                logger.debug(f"Looking up channel by name {channel_name}: {welcome_channel}")
                
            if welcome_channel is None:
                logger.warning(f"Welcome channel not found for guild {guild.name} ({guild.id})")
                return False
            
            # Check permissions
            bot_member = guild.get_member(self.bot.user.id)
            if not welcome_channel.permissions_for(bot_member).send_messages:
                logger.error(f"Missing permissions to send messages in {welcome_channel.name}")
                return False
            
            if not welcome_channel.permissions_for(bot_member).embed_links:
                logger.error(f"Missing permissions to send embeds in {welcome_channel.name}")
                return False
                
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
            try:
                if member.avatar:
                    embed.set_thumbnail(url=member.avatar.url)
                else:
                    default_avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
                    embed.set_thumbnail(url=default_avatar_url)
            except Exception as avatar_error:
                logger.error(f"Error setting avatar: {avatar_error}")
                
            # Add member info
            try:
                embed.add_field(
                    name="Member", 
                    value=f"{member.name}", 
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
            except Exception as field_error:
                logger.error(f"Error adding fields to embed: {field_error}")
            
            # Send the message
            try:
                await welcome_channel.send(welcome_message, embed=embed)
                logger.info(f"Successfully sent welcome message in {welcome_channel.name}")
                return True
            except Exception as e:
                logger.error(f"Error sending welcome message: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error in _send_welcome_message: {e}", exc_info=True)
            return False

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Handle new member joining.
        
        Args:
            member: The member who joined
        """
        try:
            if member.bot:
                logger.debug(f"Ignoring bot join event for {member.name}")
                return
                
            guild = member.guild
            guild_id = str(guild.id)
            
            logger.info(f"Member joined: {member.name} in {guild.name}")
            
            # Send welcome message
            await self._send_welcome_message(member, guild)
            
            # Assign role if configured
            await self._assign_welcome_role(member, guild)
            
        except Exception as e:
            logger.error(f"Error handling member join: {e}", exc_info=True)

    async def _assign_welcome_role(self, member: discord.Member, guild: discord.Guild):
        """
        Assign welcome role to a new member.
        
        Args:
            member: The Discord member to assign the role to
            guild: The guild (server) the member joined
        """
        try:
            guild_id = str(guild.id)
            config = self.server_config.get(guild_id, {})

            if not config:
                logger.debug(f"No welcome config for guild {guild.name} ({guild.id})")
                return

            # Get role (by ID first, then by name as fallback)
            role = None
            role_id = config.get("welcome_role_id")
            role_name = config.get("welcome_role_name")
            
            if role_id:
                role = guild.get_role(role_id)
                logger.debug(f"Looking up role by ID {role_id}: {role}")
                
            if role is None and role_name:
                role = discord.utils.get(guild.roles, name=role_name)
                logger.debug(f"Looking up role by name {role_name}: {role}")
                
            if role:
                try:
                    logger.info(f"Assigning role {role.name} to {member.name} in {guild.name}")
                    await member.add_roles(role, reason="Welcome role assignment")
                    logger.info(f"Successfully assigned role {role.name} to {member.name}")
                except discord.Forbidden:
                    logger.error(f"Cannot assign role {role.name} - missing permissions")
                    
                    # Try to notify in welcome channel
                    try:
                        welcome_channel = None
                        channel_id = config.get("welcome_channel_id")
                        
                        if channel_id:
                            welcome_channel = guild.get_channel(channel_id)
                            
                        if welcome_channel:
                            await welcome_channel.send(
                                f"⚠️ Could not give {member.mention} the {role.name} role. Bot lacks permissions."
                            )
                    except Exception as notify_error:
                        logger.error(f"Error sending notification: {notify_error}")
                        
                except discord.HTTPException as e:
                    logger.error(f"Failed to assign role {role.name}: {e}")
                    
                    # Try to notify in welcome channel
                    try:
                        welcome_channel = None
                        channel_id = config.get("welcome_channel_id")
                        
                        if channel_id:
                            welcome_channel = guild.get_channel(channel_id)
                            
                        if welcome_channel:
                            await welcome_channel.send(
                                f"⚠️ Failed to give {member.mention} the {role.name} role. An unexpected error occurred."
                            )
                    except Exception as notify_error:
                        logger.error(f"Error sending notification: {notify_error}")
        
        except Exception as e:
            logger.error(f"Error assigning welcome role: {e}", exc_info=True)

    @app_commands.command(
        name="checkwelcome", 
        description="Debug welcome configuration"
    )
    async def checkwelcome(self, interaction: discord.Interaction):
        """Debug command to check welcome configuration."""
        try:
            if not await self.check_permissions(interaction):
                return
                
            guild_id = str(interaction.guild.id)
            
            # Check if guild has config
            has_config = guild_id in self.server_config
            config_data = self.server_config.get(guild_id, {})
            
            # Check channel
            channel_id = config_data.get("welcome_channel_id")
            channel_exists = False
            channel_perms_ok = False
            
            if channel_id:
                channel = interaction.guild.get_channel(channel_id)
                channel_exists = channel is not None
                
                if channel_exists:
                    bot_perms = channel.permissions_for(interaction.guild.me)
                    channel_perms_ok = bot_perms.send_messages and bot_perms.embed_links
            
            # Check role
            role_id = config_data.get("welcome_role_id")
            role_exists = False
            role_perms_ok = False
            
            if role_id:
                role = interaction.guild.get_role(role_id)
                role_exists = role is not None
                
                if role_exists:
                    bot_role = interaction.guild.me.top_role
                    role_perms_ok = bot_role > role and interaction.guild.me.guild_permissions.manage_roles
            
            # Create diagnostic embed
            embed = discord.Embed(
                title="Welcome Configuration Diagnostics",
                description="Checking your welcome setup for issues",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Config Status",
                value=f"✅ Found" if has_config else "❌ Not configured",
                inline=False
            )
            
            if has_config:
                embed.add_field(
                    name="Welcome Channel",
                    value=(
                        f"{'✅' if channel_exists else '❌'} Exists: "
                        f"<#{channel_id}>" if channel_exists else f"ID: {channel_id}"
                    ),
                    inline=True
                )
                
                if channel_exists:
                    embed.add_field(
                        name="Channel Permissions",
                        value="✅ OK" if channel_perms_ok else "❌ Missing permissions",
                        inline=True
                    )
                
                if role_id:
                    embed.add_field(
                        name="Welcome Role",
                        value=(
                            f"{'✅' if role_exists else '❌'} Exists: "
                            f"{role.name}" if role_exists else f"ID: {role_id}"
                        ),
                        inline=True
                    )
                    
                    if role_exists:
                        embed.add_field(
                            name="Role Permissions",
                            value="✅ OK" if role_perms_ok else "❌ Role hierarchy issue or missing permissions",
                            inline=True
                        )
                
                embed.add_field(
                    name="Welcome Message",
                    value="✅ Configured" if "welcome_message" in config_data else "⚠️ Using default",
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in checkwelcome: {e}", exc_info=True)
            await interaction.response.send_message(
                f"An error occurred during diagnostics: {e}",
                ephemeral=True
            )

async def setup(bot: commands.Bot, config=None):
    """
    Setup function to register the cog with the bot.
    
    Args:
        bot: The Discord bot instance
        config: Optional configuration object
    """
    try:
        cog = Welcome(bot, config)
        await bot.add_cog(cog)
        logger.info("Welcome Cog loaded!")
        
        # List all registered commands for this cog
        if hasattr(cog, "__cog_app_commands__"):
            for cmd in cog.__cog_app_commands__:
                logger.info(f"  - Registered command: {cmd.name}")
                
        return cog
    except Exception as e:
        logger.error(f"Error setting up Welcome cog: {e}", exc_info=True)
        return None