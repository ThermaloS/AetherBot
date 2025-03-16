# MAIN IMPORTS
import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import sys

# UTILITY IMPORTS
from bin.utils.config import BotConfig
from bin.utils.logging_setup import setup_logging

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("ERROR: DISCORD_TOKEN environment variable not set!")
    sys.exit(1)

# Initialize configuration and logging
config = BotConfig()
logger = setup_logging()

# Setting Discord Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

# Bot Initialization
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    """Handles the bot's ready event."""
    logger.info(f"{bot.user} is online!")
    
    # Set bot status
    activity = discord.Activity(
        type=discord.ActivityType.watching, 
        name=config.get("general", "status_message", "over your server!")
    )
    await bot.change_presence(activity=activity)
    
    # Sync commands
    try:
        logger.info("Syncing application commands...")
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s) globally")
        for command in synced:
            logger.info(f"  - {command.name}")
    except Exception as e:
        logger.error(f"Error syncing commands: {e}")

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for traditional commands."""
    logger.error(f"Command error in {ctx.command}: {error}")
    
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: {error.param.name}")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"Bad argument: {error}")
    else:
        await ctx.send(f"An error occurred: {error}")

async def setup_cogs():
    """Load all cogs."""
    logger.info("Setting up cogs...")
    
    # Create MusicCog first as it's a dependency for other cogs
    from bin.cogs.music.music_cog import MusicCog, setup as music_setup
    music_cog = MusicCog(bot, config)
    await music_setup(bot, config)
    logger.info("Core MusicCog loaded")
    
    # Music-related cogs
    try:
        from bin.cogs.music.commands.music_general_controls import setup as general_controls_setup
        from bin.cogs.music.commands.music_play_commands import setup as play_commands_setup
        from bin.cogs.music.commands.music_elevated_commands import setup as elevated_commands_setup
        from bin.cogs.music.radiocog import setup as radio_setup
        
        await general_controls_setup(bot, music_cog)
        await play_commands_setup(bot, music_cog)
        await elevated_commands_setup(bot, music_cog)
        await radio_setup(bot, music_cog, config)
        logger.info("Music commands and RadioCog loaded")
    except Exception as e:
        logger.error(f"Error loading music cogs: {e}")
    
    # General bot cogs
    try:
        from bin.cogs.moderation.welcome_cog import setup as welcome_setup
        from bin.cogs.utility.misc_commands_cog import setup as server_setup
        
        await welcome_setup(bot, config)
        await server_setup(bot)
        logger.info("General bot cogs loaded")
    except Exception as e:
        logger.error(f"Error loading general cogs: {e}")
    
    # Gemini integration (optional)
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if gemini_api_key:
        try:
            from bin.services.gemini_cog import setup as gemini_setup
            await gemini_setup(bot)
            logger.info("Gemini cog loaded")
        except Exception as e:
            logger.error(f"Error loading Gemini cog: {e}")
    else:
        logger.warning("GEMINI_API_KEY not found. Gemini features will not be available.")

async def main():
    """Main entry point for the bot."""
    try:
        # Setup cogs
        await setup_cogs()
        
        # Start the bot
        logger.info("Starting bot...")
        await bot.start(TOKEN)
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
    finally:
        # Clean shutdown
        if not bot.is_closed():
            await bot.close()
        logger.info("Bot has been shut down")

if __name__ == "__main__":
    asyncio.run(main())