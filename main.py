import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio
import sys
import logging
import traceback
from typing import Optional, Type, Any, Callable, Coroutine

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

async def load_cog(
    bot: commands.Bot, 
    cog_class: Type[commands.Cog], 
    *args: Any
) -> Optional[commands.Cog]:
    """
    Load a cog with dependency injection.
    
    Args:
        bot: The bot instance
        cog_class: The cog class to instantiate
        *args: Arguments to pass to the cog constructor
    
    Returns:
        The loaded cog instance or None if loading failed
    """
    try:
        cog_instance = cog_class(bot, *args)
        await bot.add_cog(cog_instance)
        logger.info(f"Loaded {cog_class.__name__}")
        return cog_instance
    except Exception as e:
        logger.error(f"Error loading {cog_class.__name__}: {e}")
        logger.debug(traceback.format_exc())
        return None

async def setup_cogs():
    """Load all cogs with proper dependency injection."""
    logger.info("Setting up cogs...")
    
    # Import cog classes here to avoid circular imports
    # Core services
    from bin.services.youtube_service import YouTubeService
    youtube_service = YouTubeService(config)
    
    # Music system
    try:
        from bin.cogs.music.music_cog import MusicCog
        from bin.cogs.music.commands.music_general_controls import GeneralMusicControls
        from bin.cogs.music.commands.music_play_commands import AddSongs
        from bin.cogs.music.commands.music_elevated_commands import ElevatedMusicCommands
        from bin.cogs.music.radiocog import RadioCog
        
        # Load MusicCog first as a dependency for other music cogs
        # Fix: Pass config as a parameter to MusicCog
        music_cog = await load_cog(bot, MusicCog, config)
        if not music_cog:
            logger.error("Failed to load core MusicCog, skipping related music cogs")
            return
        
        # Load music command cogs with MusicCog dependency
        await load_cog(bot, GeneralMusicControls, music_cog)
        await load_cog(bot, AddSongs, music_cog)
        await load_cog(bot, ElevatedMusicCommands, music_cog)
        
        # Load RadioCog with dependencies
        await load_cog(bot, RadioCog, music_cog, config)
        
        logger.info("Music system loaded successfully")
    except Exception as e:
        logger.error(f"Failed to set up music system: {e}")
        logger.debug(traceback.format_exc())
    
    # Utility and moderation cogs
    try:
        from bin.cogs.moderation.welcome_cog import Welcome
        from bin.cogs.utility.misc_commands_cog import ServerCog
        
        await load_cog(bot, Welcome)
        await load_cog(bot, ServerCog)
        
        logger.info("Utility and moderation cogs loaded successfully")
    except Exception as e:
        logger.error(f"Failed to set up utility cogs: {e}")
        logger.debug(traceback.format_exc())
    
    # Optional integrations
    if os.getenv("GEMINI_API_KEY"):
        try:
            from bin.services.gemini_cog import GeminiCog
            await load_cog(bot, GeminiCog)
            logger.info("Gemini integration loaded successfully")
        except Exception as e:
            logger.error(f"Failed to set up Gemini integration: {e}")
            logger.debug(traceback.format_exc())
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
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        logger.debug(traceback.format_exc())
    finally:
        # Clean shutdown
        if not bot.is_closed():
            await bot.close()
        logger.info("Bot has been shut down")

if __name__ == "__main__":
    asyncio.run(main())