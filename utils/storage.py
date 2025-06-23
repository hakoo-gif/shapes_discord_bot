import json
import os
import aiofiles
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class DataStorage:
    """Handles JSON-based data storage for the bot"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # File paths
        self.server_settings_file = self.data_dir / "server_settings.json"
        self.user_auth_file = self.data_dir / "user_auth.json"
        self.blocked_users_file = self.data_dir / "blocked_users.json"
        
        # Initialize files if they don't exist
        self._init_files()
    
    def _init_files(self):
        """Initialize data files with default structures"""
        default_data = {
            "server_settings.json": {},
            "user_auth.json": {},
            "blocked_users.json": {},
            "revive_chat.json": {}
        }
        
        for filename, default_content in default_data.items():
            filepath = self.data_dir / filename
            if not filepath.exists():
                try:
                    with open(filepath, 'w') as f:
                        json.dump(default_content, f, indent=2)
                except Exception as e:
                    logger.error(f"Failed to initialize {filename}: {e}")
    
    async def _read_json(self, filepath: Path) -> Dict[str, Any]:
        """Read JSON data from file"""
        try:
            if not filepath.exists():
                return {}
            
            async with aiofiles.open(filepath, 'r') as f:
                content = await f.read()
                return json.loads(content) if content.strip() else {}
        except Exception as e:
            logger.error(f"Error reading {filepath}: {e}")
            return {}
    
    async def _write_json(self, filepath: Path, data: Dict[str, Any]):
        """Write JSON data to file"""
        try:
            async with aiofiles.open(filepath, 'w') as f:
                await f.write(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Error writing {filepath}: {e}")
    
    # Server Settings Methods
    async def get_server_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get server settings"""
        data = await self._read_json(self.server_settings_file)
        return data.get(str(guild_id), {
            "activated": False,
            "blacklist": [],
            "whitelist": [],
            "use_blacklist": False  # True for blacklist, False for whitelist
        })
    
    async def update_server_settings(self, guild_id: int, settings: Dict[str, Any]):
        """Update server settings"""
        data = await self._read_json(self.server_settings_file)
        data[str(guild_id)] = settings
        await self._write_json(self.server_settings_file, data)
    
    async def set_server_activation(self, guild_id: int, activated: bool):
        """Set server activation status"""
        settings = await self.get_server_settings(guild_id)
        settings["activated"] = activated
        await self.update_server_settings(guild_id, settings)
    
    async def add_to_blacklist(self, guild_id: int, channel_id: int):
        """Add channel to blacklist and switch to blacklist mode"""
        settings = await self.get_server_settings(guild_id)
        if channel_id not in settings["blacklist"]:
            settings["blacklist"].append(channel_id)
        
        # Switch to blacklist mode and clear whitelist
        settings["use_blacklist"] = True
        settings["whitelist"] = []
        await self.update_server_settings(guild_id, settings)

    async def remove_from_blacklist(self, guild_id: int, channel_id: int):
        """Remove channel from blacklist"""
        settings = await self.get_server_settings(guild_id)
        if channel_id in settings["blacklist"]:
            settings["blacklist"].remove(channel_id)
            await self.update_server_settings(guild_id, settings)

    async def add_to_whitelist(self, guild_id: int, channel_id: int):
        """Add channel to whitelist and switch to whitelist mode"""
        settings = await self.get_server_settings(guild_id)
        if channel_id not in settings["whitelist"]:
            settings["whitelist"].append(channel_id)
        
        # Switch to whitelist mode and clear blacklist
        settings["use_blacklist"] = False
        settings["blacklist"] = []
        await self.update_server_settings(guild_id, settings)

    async def remove_from_whitelist(self, guild_id: int, channel_id: int):
        """Remove channel from whitelist"""
        settings = await self.get_server_settings(guild_id)
        if channel_id in settings["whitelist"]:
            settings["whitelist"].remove(channel_id)
            await self.update_server_settings(guild_id, settings)
    
    # User Auth Methods
    async def get_user_auth(self, user_id: int) -> Optional[Dict[str, str]]:
        """Get user authentication data (app_id and auth_token)"""
        data = await self._read_json(self.user_auth_file)
        return data.get(str(user_id))
    
    async def set_user_auth(self, user_id: int, auth_data: Dict[str, str]):
        """Set user authentication data"""
        data = await self._read_json(self.user_auth_file)
        data[str(user_id)] = auth_data
        await self._write_json(self.user_auth_file, data)
    
    async def remove_user_auth(self, user_id: int) -> bool:
        """Remove user authentication data"""
        data = await self._read_json(self.user_auth_file)
        if str(user_id) in data:
            del data[str(user_id)]
            await self._write_json(self.user_auth_file, data)
            return True
        return False
    
    # Blocked Users Methods
    async def get_blocked_users(self, guild_id: int) -> List[int]:
        """Get list of blocked users for a guild"""
        data = await self._read_json(self.blocked_users_file)
        return data.get(str(guild_id), [])
    
    async def block_user(self, guild_id: int, user_id: int):
        """Block a user in a guild"""
        data = await self._read_json(self.blocked_users_file)
        if str(guild_id) not in data:
            data[str(guild_id)] = []
        
        if user_id not in data[str(guild_id)]:
            data[str(guild_id)].append(user_id)
            await self._write_json(self.blocked_users_file, data)
    
    async def unblock_user(self, guild_id: int, user_id: int):
        """Unblock a user in a guild"""
        data = await self._read_json(self.blocked_users_file)
        if str(guild_id) in data and user_id in data[str(guild_id)]:
            data[str(guild_id)].remove(user_id)
            await self._write_json(self.blocked_users_file, data)
    
    async def is_user_blocked(self, guild_id: int, user_id: int) -> bool:
        """Check if a user is blocked in a guild"""
        blocked_users = await self.get_blocked_users(guild_id)
        return user_id in blocked_users
    
    # Trigger Words Methods
    async def get_server_trigger_words(self, guild_id: int) -> List[str]:
        """Get server-specific trigger words"""
        try:
            settings = await self.get_server_settings(guild_id)
            return settings.get("server_trigger_words", [])
        except Exception as e:
            logger.error(f"Error getting server trigger words: {e}")
            return []

    async def add_server_trigger_word(self, guild_id: int, word: str) -> bool:
        """Add a server-specific trigger word"""
        try:
            settings = await self.get_server_settings(guild_id)
            if "server_trigger_words" not in settings:
                settings["server_trigger_words"] = []
            
            word = word.strip().lower()
            if word and word not in settings["server_trigger_words"]:
                settings["server_trigger_words"].append(word)
                await self.update_server_settings(guild_id, settings)
                return True
            return False
        except Exception as e:
            logger.error(f"Error adding server trigger word: {e}")
            return False

    async def remove_server_trigger_word(self, guild_id: int, word: str) -> bool:
        """Remove a server-specific trigger word"""
        try:
            settings = await self.get_server_settings(guild_id)
            server_trigger_words = settings.get("server_trigger_words", [])
            
            word = word.strip().lower()
            if word in server_trigger_words:
                settings["server_trigger_words"].remove(word)
                await self.update_server_settings(guild_id, settings)
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing server trigger word: {e}")
            return False

    # Channel Activation Methods
    async def set_channel_activation(self, guild_id: int, channel_id: int, enabled: bool):
        """Set channel-specific activation status"""
        try:
            settings = await self.get_server_settings(guild_id)
            if "activated_channels" not in settings:
                settings["activated_channels"] = {}
            
            settings["activated_channels"][str(channel_id)] = enabled
            await self.update_server_settings(guild_id, settings)
        except Exception as e:
            logger.error(f"Error setting channel activation: {e}")

    async def is_channel_activated(self, guild_id: int, channel_id: int) -> bool:
        """Check if a specific channel is activated"""
        try:
            settings = await self.get_server_settings(guild_id)
            activated_channels = settings.get("activated_channels", {})
            return activated_channels.get(str(channel_id), False)
        except Exception as e:
            logger.error(f"Error checking channel activation: {e}")
            return False
        
    # Revive Chat Methods
    async def get_revive_chat_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get revive chat settings for a guild"""
        try:
            data = await self._read_json(self.revive_chat_file)
            return data.get(str(guild_id), {
                'enabled': False,
                'channel_id': None,
                'role_id': None,
                'interval_minutes': 60,
                'next_send_time': None
            })
        except Exception as e:
            logger.error(f"Error getting revive chat settings: {e}")
            return {
                'enabled': False,
                'channel_id': None,
                'role_id': None,
                'interval_minutes': 60,
                'next_send_time': None
            }

    async def set_revive_chat_settings(self, guild_id: int, settings: Dict[str, Any]):
        """Set revive chat settings for a guild"""
        try:
            data = await self._read_json(self.revive_chat_file)
            data[str(guild_id)] = settings
            await self._write_json(self.revive_chat_file, data)
        except Exception as e:
            logger.error(f"Error setting revive chat settings: {e}")

    async def update_revive_chat_next_time(self, guild_id: int, next_time: str):
        """Update the next send time for revive chat"""
        try:
            data = await self._read_json(self.revive_chat_file)
            if str(guild_id) in data:
                data[str(guild_id)]['next_send_time'] = next_time
                await self._write_json(self.revive_chat_file, data)
        except Exception as e:
            logger.error(f"Error updating revive chat next time: {e}")

    async def disable_revive_chat(self, guild_id: int):
        """Disable revive chat for a guild"""
        try:
            data = await self._read_json(self.revive_chat_file)
            if str(guild_id) in data:
                data[str(guild_id)]['enabled'] = False
                await self._write_json(self.revive_chat_file, data)
        except Exception as e:
            logger.error(f"Error disabling revive chat: {e}")
            
    # Bot-to-Bot Conversation Methods
    async def set_bot_to_bot_enabled(self, guild_id: int, channel_id: int, enabled: bool):
        """Set bot-to-bot conversation status for a specific channel"""
        try:
            settings = await self.get_server_settings(guild_id)
            if "bot_to_bot_channels" not in settings:
                settings["bot_to_bot_channels"] = {}
            
            settings["bot_to_bot_channels"][str(channel_id)] = enabled
            await self.update_server_settings(guild_id, settings)
        except Exception as e:
            logger.error(f"Error setting bot-to-bot status: {e}")

    async def is_bot_to_bot_enabled(self, guild_id: int, channel_id: int) -> bool:
        """Check if bot-to-bot conversation is enabled for a specific channel"""
        try:
            settings = await self.get_server_settings(guild_id)
            bot_to_bot_channels = settings.get("bot_to_bot_channels", {})
            return bot_to_bot_channels.get(str(channel_id), False)
        except Exception as e:
            logger.error(f"Error checking bot-to-bot status: {e}")
            return False
