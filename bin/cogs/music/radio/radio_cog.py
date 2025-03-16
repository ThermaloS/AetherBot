import logging
from discord.ext import commands

# Local imports
from bin.cogs.music.music_cog import MusicCog
from bin.cogs.music.radio.radio_core import RadioCore
from bin.cogs.music.radio.radio_commands import RadioCommands
from bin.cogs.music.radio.radio_service import RadioService
from bin.services.youtube_service import YouTubeService
from bin.utils.title_processor import TitleProcessor

logger = logging.getLogger('discord_bot.radio')

class RadioCog(commands.Cog):
    """
    Discord bot cog for radio-like music playback (autoplay).
    This is the main entry point that ties together all radio components.
    """
    
    def __init__(self, bot: commands.Bot, music_cog: MusicCog, config=None):
        """
        Initialize the radio cog with all required components.
        
        Args:
            bot: The bot instance
            music_cog: The main MusicCog instance for music playback
            config: Optional configuration object
        """
        self.bot = bot
        self.music_cog = music_cog
        self.config = config
        
        # Initialize title processor
        self.title_processor = TitleProcessor(config if config else {})
        
        # Initialize YouTube service
        self.youtube_service = YouTubeService(config, self.title_processor)
        
        # Initialize core radio functionality
        self.radio_core = RadioCore(bot, music_cog, config)
        
        # Initialize radio service for recommendations
        self.radio_service = RadioService(self.radio_core, self.youtube_service, self.title_processor)
        
        # Store the components but don't register them yet
        # They will be registered in the async setup_components method
        self.radio_commands = None
        
        logger.info("RadioCog initialized - components ready for setup")
        super().__init__()
    
    async def setup_components(self):
        """Asynchronously set up and register all radio components."""
        # Register the core functionality as a cog
        await self.bot.add_cog(self.radio_core)
        
        # Initialize and register commands
        try:
            self.radio_commands = RadioCommands(self.bot, self.radio_core)
            await self.bot.add_cog(self.radio_commands)
            logger.info("Radio commands registered")
            
            # Verify the commands exist on the cog
            for command in self.radio_commands.__cog_app_commands__:
                logger.info(f"Radio command registered: {command.name}")
        except Exception as e:
            logger.error(f"Error registering radio commands: {e}")
        
        logger.info("RadioCog components setup complete")
    
    def is_radio_enabled(self, guild_id: int) -> bool:
        """
        Check if radio mode is enabled for a guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            True if radio mode is enabled, False otherwise
        """
        return self.radio_core.is_radio_enabled(guild_id)
    
    async def add_similar_songs_to_queue(self, query: str, guild_id: int, channel):
        """
        Add similar songs to the queue.
        
        Args:
            query: Original query or URL of the reference song
            guild_id: Discord guild ID
            channel: Text channel for sending messages
            
        Returns:
            List of (url, title) tuples added to the queue
        """
        return await self.radio_service.add_similar_songs_to_queue(query, guild_id, channel)

    @classmethod
    async def setup(cls, bot: commands.Bot, music_cog=None, config=None):
        """
        Setup function to register the cog with the bot.
        
        Args:
            cls: The RadioCog class
            bot: The Discord bot instance
            music_cog: The MusicCog instance
            config: Optional configuration object
        """
        if music_cog is None:
            # Try to get the music cog if it wasn't passed
            music_cog = bot.get_cog("MusicCog")
            if music_cog is None:
                logger.error("MusicCog not found. Cannot load RadioCog.")
                return None
                
        # Create the RadioCog instance
        cog = cls(bot, music_cog, config)
        
        # Register the main cog
        await bot.add_cog(cog)
        
        # Set up all components asynchronously
        await cog.setup_components()
        
        # Register commands explicitly
        try:
            # Force a sync of application commands
            await bot.tree.sync()
            logger.info("Radio commands synced globally")
        except Exception as e:
            logger.error(f"Error syncing radio commands: {e}")
        
        logger.info("RadioCog loaded successfully")
        return cog