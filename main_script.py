# MAIN IMPORTS
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import os
import asyncio
# GENERAL BOT FUNCTIONS
from bin.cogs.welcome_cog import setup as welcome_setup
from bin.cogs.commands.misc_commands_cog import setup as server_setup
# GEMINI IMPORTS
from bin.cogs.gemini_cog import setup as gemini_setup
# MUSIC IMPORTS (CORE LOGIC AND COMMANDS)
from bin.cogs.music_cog import MusicCog, setup as music_setup
from bin.cogs.commands.music_general_controls import setup as general_controls_setup
from bin.cogs.commands.music_play_commands import setup as play_commands_setup
from bin.cogs.commands.music_elevated_commands import setup as elevated_commands_setup
    

# Logging Setup
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Environment Variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
YOUR_GUILD_ID = os.getenv("YOUR_GUILD_ID")  # Not used in this example, but kept
YOUR_WELCOME_CHANNEL_ID = os.getenv("YOUR_WELCOME_CHANNEL_ID")  # Not used here
YOUR_ROLE_ID = os.getenv("YOUR_ROLE_ID")  # Not used here
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Not used here
# Setting Intents (Good as-is)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Needed for on_member_join events (if you use it)
intents.voice_states = True

# Bot Initialization
bot = commands.Bot(command_prefix="!", intents=intents)

# No longer needed: bot.synced = False

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    print("on_ready event triggered.")  # Add this line
    try:
        print("Attempting to sync commands...") #add this line
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s) globally.")
        for command in synced:
            print(f"  - {command.name}")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    print("on_ready event finished.") #add this line

# Main Function
async def main():
    # 1. Create the MusicCog instance
    music_cog = MusicCog(bot)

    # 2. Load the cogs using their setup functions.
    await music_setup(bot)  # Load MusicCog (core logic)
    # Music Commands
    await general_controls_setup(bot, music_cog)
    await play_commands_setup(bot, music_cog)
    await elevated_commands_setup(bot, music_cog)
    # General Bot Setup
    await welcome_setup(bot)
    await server_setup(bot)
    # Gemini API Setup
    await gemini_setup(bot)

    # 3. Start the bot using bot.start() within the async main function.
    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())  # Use asyncio.run to start the async main functionpip