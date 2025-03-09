import discord
from discord.ext import commands
from discord import app_commands
import traceback  # For more detailed error logging
from typing import List

class ServerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.server_links = {
            "grandforksspartans": {
                "link": "https://discord.gg/qrKanm6dF7",
                "display_name": "Grand Forks Spartans"
            },
            # Add more servers here
        }

    async def server_name_autocomplete(  # Moved this function definition UP
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
    @app_commands.autocomplete(server_name=server_name_autocomplete) # Now this works
    async def server(self, interaction: discord.Interaction, server_name: str):
        """Provides a link to a specified server."""

        server_name = server_name.lower()

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
            traceback.print_exc()  # Print the full traceback
            await interaction.response.send_message(
                "An unexpected error occurred.  Please try again later.", ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(ServerCog(bot))