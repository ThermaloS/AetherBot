import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger('discord_bot.config')

class BotConfig:
    """Centralized configuration management for the Discord bot."""
    
    def __init__(self, config_file: str = "bot_config.json"):
        self.config_file = config_file
        self.config: Dict[str, Any] = {}
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        self.config = json.loads(content)
                    else:
                        self.config = self._create_default_config()
            else:
                self.config = self._create_default_config()
                self.save_config()
                logger.info(f"Created new configuration file: {self.config_file}")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            self.config = self._create_default_config()
    
    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        if section in self.config and key in self.config[section]:
            return self.config[section][key]
        return default
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get an entire configuration section."""
        return self.config.get(section, {})
    
    def set(self, section: str, key: str, value: Any) -> None:
        """Set a configuration value."""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
        self.save_config()
    
    def get_guild_config(self, guild_id: str) -> Dict[str, Any]:
        """Get guild-specific configuration."""
        return self.config.get("guilds", {}).get(guild_id, {})
    
    def set_guild_config(self, guild_id: str, key: str, value: Any) -> None:
        """Set guild-specific configuration."""
        if "guilds" not in self.config:
            self.config["guilds"] = {}
        if guild_id not in self.config["guilds"]:
            self.config["guilds"][guild_id] = {}
        self.config["guilds"][guild_id][key] = value
        self.save_config()
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default configuration."""
        return {
            "music": {
                "default_volume": 0.05,
                "max_queue_size": 100,
                "similarity_threshold": 0.6,
                "compilation_keywords": [
                    "compilation", "mix", "best of", "top 10", "top ten", 
                    "playlist", "album mix", "full album", "megamix"
                ]
            },
            "welcome": {
                # Default welcome settings
            },
            "general": {
                # General bot settings
            },
            "guilds": {
                # Guild-specific settings will be stored here
            }
        }