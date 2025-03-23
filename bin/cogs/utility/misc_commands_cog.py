import discord
from discord.ext import commands
from discord import app_commands
import traceback
import json
import os
from typing import List

class ServerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.server_links_file = 'server_links.json'
        self.server_links = self.load_server_links()

    def load_server_links(self) -> dict:
        """Load server links from a JSON file."""
        if os.path.exists(self.server_links_file):
            with open(self.server_links_file, 'r') as f:
                return json.load(f)
        return {}

    def save_server_links(self):
        """Save server links to a JSON file."""
        with open(self.server_links_file, 'w') as f:
            json.dump(self.server_links, f, indent=4)

    async def server_name_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str,
    ) -> List[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=server_data["display_name"], value=server_key)
            for server_key, server_data in self.server_links.items()
            if current.lower() in server_key.lower() or current.lower() in server_data["display_name"].lower()
        ]

    @app_commands.command(name="server", description="Get the link to a specific server.")
    @app_commands.describe(server_name="The name of the server.")
    @app_commands.autocomplete(server_name=server_name_autocomplete)
    async def server(self, interaction: discord.Interaction, server_name: str):
        """Provides a link to a specified server."""

        if server_name in self.server_links:
            server_data = self.server_links[server_name]
            link = server_data["link"]
            display_name = server_data["display_name"]

            await interaction.response.send_message(f"This is the link to the {display_name}: {link}")
        else:
            available_servers = ", ".join(
                [f"`{server}`" for server in self.server_links]
            )
            await interaction.response.send_message(
                f"Sorry, I couldn't find a server named '{server_name}'.  Available servers: {available_servers}",
                ephemeral=True,
            )

    @server.error
    async def server_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingRequiredArgument):
            await interaction.response.send_message("You need to specify a server name!  Use `/server <server_name>`.", ephemeral=True)
        else:
            print(f"An error occurred in the /server command: {error}")
            traceback.print_exc()
            await interaction.response.send_message(
                "An unexpected error occurred.  Please try again later.", ephemeral=True
            )

    @app_commands.command(name="add_server", description="Add a new server link (Owner only).")
    @app_commands.describe(server_name="The name of the server.", link="The invite link to the server.")
    async def add_server(self, interaction: discord.Interaction, server_name: str, link: str):
        """Adds a new server link to the server_links dictionary (Owner only)."""
        if interaction.user.id != self.bot.owner_id:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        self.server_links[server_name] = {"display_name": server_name, "link": link}
        self.save_server_links()
        await interaction.response.send_message(f"Server '{server_name}' added successfully with link: {link}")

    @add_server.error
    async def add_server_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        print(f"An error occurred in the /add_server command: {error}")
        traceback.print_exc()
        await interaction.response.send_message(
            "An unexpected error occurred.  Please try again later.", ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(ServerCog(bot))