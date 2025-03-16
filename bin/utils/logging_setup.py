import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Configure logging for the entire application."""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Set up root logger
    logger = logging.getLogger('discord_bot')
    logger.setLevel(logging.INFO)
    
    # Prevent duplicate handlers on reload
    if logger.handlers:
        return logger
    
    # Format for logs
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler - for general info
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler - for info and above
    file_handler = RotatingFileHandler(
        'logs/bot.log', 
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Error file handler - for errors only
    error_handler = RotatingFileHandler(
        'logs/errors.log',
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    
    # Configure discord.py's logger
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.WARNING)  # Only warnings and errors
    
    # Add the handlers to discord.py's logger too
    for handler in logger.handlers:
        discord_logger.addHandler(handler)
    
    logger.info("Logging system initialized")
    return logger