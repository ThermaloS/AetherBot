import discord
from discord.ext import commands
import json

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_config()

    def load_config(self):
        try:
            with open("server_config.json", "r") as f:
                self.server_config = json.load(f)
        except FileNotFoundError:
            self.server_config = {}

    def save_config(self):
        with open("server_config.json", "w") as f:
            json.dump(self.server_config, f, indent=4)

    async def check_permissions(self, interaction: discord.Interaction):
        """Checks if the user has both Manage Channels and Manage Roles permissions."""
        if interaction.user.guild_permissions.manage_channels and interaction.user.guild_permissions.manage_roles:
            return True
        else:
            await interaction.response.send_message("You need both 'Manage Channels' and 'Manage Roles' permissions to use this command.", ephemeral=True)
            return False

    @discord.app_commands.command(name="setwelcomechannel", description="Sets the welcome channel for this server.")
    async def setwelcomechannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Sets the welcome channel for this server."""
        if not await self.check_permissions(interaction):
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.server_config:
            self.server_config[guild_id] = {}
        self.server_config[guild_id]["welcome_channel_name"] = channel.name
        self.save_config()
        await interaction.response.send_message(f"Welcome channel set to {channel.mention}", ephemeral=True)

    @discord.app_commands.command(name="setwelcomerole", description="Sets the welcome role for this server.")
    async def setwelcomerole(self, interaction: discord.Interaction, role: discord.Role):
        """Sets the welcome role for this server."""
        if not await self.check_permissions(interaction):
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.server_config:
            self.server_config[guild_id] = {}
        self.server_config[guild_id]["welcome_role_name"] = role.name
        self.save_config()
        await interaction.response.send_message(f"Welcome role set to {role.name}", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Welcomes a new member and gives them a role."""
        guild_id = str(member.guild.id)
        config = self.server_config.get(guild_id)

        if not config:
            return

        welcome_channel_name = config.get("welcome_channel_name")
        welcome_role_name = config.get("welcome_role_name")

        # Add some debugging info
        print(f"Welcome Channel: {welcome_channel_name}")
        print(f"Welcome Role: {welcome_role_name}")

        welcome_channel = discord.utils.get(member.guild.text_channels, name=welcome_channel_name)
        role = discord.utils.get(member.guild.roles, name=welcome_role_name)
        guild_name = member.guild.name

        print(f"Welcome Channel Object: {welcome_channel}") # Debugging Line
        print(f"Welcome Role Object: {role}") # Debugging Line

        if welcome_channel:
            welcome_message = f"Welcome to the {guild_name}, {member.mention}!"
            
            embed = discord.Embed(
                title=f"Welcome to the {guild_name}!",
                description=f"We're glad to have you here, {member.mention}!",
                color=discord.Color.green()
            )
            if member.avatar:
                # Use Members Profile Picture
                embed.set_thumbnail(url=member.avatar.url)
            else:
                # Use Discord's Default Profile Picture
                default_avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
                embed.set_thumbnail(url=default_avatar_url)

            print(f"Attempting to send welcome message to channel: {welcome_channel.name} ({welcome_channel.id})") # Debugging Line
            print(f"Welcome Message Content: {welcome_message}") # Debugging Line
            print(f"Embed Title: {embed.title}, Embed Description: {embed.description}") # Debugging Line
            try:
                await welcome_channel.send(welcome_message, embed=embed) # Send the plain text message and then the embed
                print("Welcome message sent successfully!") # Debugging Line
            except Exception as e:
                print(f"Error sending welcome message: {e}") # Debugging Line

        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                if welcome_channel:
                    await welcome_channel.send(f"Could not give {member.mention} the {role.name} role. Bot lacks permissions.")
            except discord.HTTPException:
                if welcome_channel:
                    await welcome_channel.send(f"Failed to give {member.mention} the {role.name} role. An unexpected error occurred.")


async def setup(bot):
    await bot.add_cog(Welcome(bot))
    print("Welcome Cog loaded!")