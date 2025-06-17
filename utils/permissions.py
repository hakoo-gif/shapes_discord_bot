import discord
import logging
from typing import List, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class PermissionLevel(Enum):
    """Permission levels for commands"""
    EVERYONE = 0
    SELECTED_ROLES = 1
    ADMIN = 2
    SERVER_OWNER = 3
    BOT_OWNER = 4

class PermissionManager:
    """Manages permissions for bot commands"""
    
    def __init__(self, bot, storage):
        self.bot = bot
        self.storage = storage
    
    def is_bot_owner(self, user_id: int) -> bool:
        """Check if user is the bot owner"""
        return (hasattr(self.bot, 'bot_owner_id') and 
                self.bot.bot_owner_id is not None and 
                user_id == self.bot.bot_owner_id)
    
    def is_server_owner(self, user: discord.Member) -> bool:
        """Check if user is the server owner"""
        return user.id == user.guild.owner_id
    
    def has_admin_permissions(self, user: discord.Member) -> bool:
        """Check if user has administrator or manage server permissions"""
        return user.guild_permissions.administrator or user.guild_permissions.manage_guild
    
    async def has_selected_role_permissions(self, user: discord.Member, command_name: str) -> bool:
        """Check if user has any of the selected roles for the command"""
        try:
            settings = await self.storage.get_server_settings(user.guild.id)
            command_roles = settings.get("command_roles", {}).get(command_name, [])
            
            if not command_roles:
                return False
            
            user_role_ids = [role.id for role in user.roles]
            return any(role_id in user_role_ids for role_id in command_roles)
        except Exception as e:
            logger.error(f"Error checking selected role permissions: {e}")
            return False
    
    async def check_permission(self, user: discord.Member, command_name: str, 
                             required_level: PermissionLevel) -> tuple[bool, str]:
        """
        Check if user has permission to use a command
        Returns: (has_permission: bool, error_message: str)
        """
        try:
            # Bot owner has access to everything
            if self.is_bot_owner(user.id):
                return True, ""
            
            # Check based on required permission level
            if required_level == PermissionLevel.EVERYONE:
                return True, ""
            
            elif required_level == PermissionLevel.BOT_OWNER:
                if not hasattr(self.bot, 'bot_owner_id') or self.bot.bot_owner_id is None:
                    # No bot owner set, fall back to server owner
                    if self.is_server_owner(user):
                        return True, ""
                    return False, "❌ You need to be the server owner to use this command."
                else:
                    return False, "❌ You need to be the bot owner to use this command."
            
            elif required_level == PermissionLevel.SERVER_OWNER:
                if self.is_server_owner(user):
                    return True, ""
                elif self.has_admin_permissions(user):
                    return True, ""
                elif await self.has_selected_role_permissions(user, command_name):
                    return True, ""
                else:
                    return False, self._get_permission_error_message(command_name)
            
            elif required_level == PermissionLevel.ADMIN:
                if self.is_server_owner(user):
                    return True, ""
                elif self.has_admin_permissions(user):
                    return True, ""
                elif await self.has_selected_role_permissions(user, command_name):
                    return True, ""
                else:
                    return False, self._get_permission_error_message(command_name)
            
            elif required_level == PermissionLevel.SELECTED_ROLES:
                if self.is_server_owner(user):
                    return True, ""
                elif self.has_admin_permissions(user):
                    return True, ""
                elif await self.has_selected_role_permissions(user, command_name):
                    return True, ""
                else:
                    return False, self._get_permission_error_message(command_name)
            
            return False, "❌ Permission check failed."
            
        except Exception as e:
            logger.error(f"Error checking permissions for {command_name}: {e}")
            return False, "❌ An error occurred while checking permissions."
    
    def _get_permission_error_message(self, command_name: str) -> str:
        """Get appropriate error message for permission denial"""
        if hasattr(self.bot, 'bot_owner_id') and self.bot.bot_owner_id is not None:
            return (f"❌ You need to be the bot owner, server owner, have Administrator/Manage Server "
                   f"permissions, or have a role with permission to use `/{command_name}`.")
        else:
            return (f"❌ You need to be the server owner, have Administrator/Manage Server "
                   f"permissions, or have a role with permission to use `/{command_name}`.")
    
    async def add_command_role(self, guild_id: int, command_name: str, role_id: int):
        """Add a role to command permissions"""
        try:
            settings = await self.storage.get_server_settings(guild_id)
            if "command_roles" not in settings:
                settings["command_roles"] = {}
            if command_name not in settings["command_roles"]:
                settings["command_roles"][command_name] = []
            
            if role_id not in settings["command_roles"][command_name]:
                settings["command_roles"][command_name].append(role_id)
                await self.storage.update_server_settings(guild_id, settings)
                return True
            return False
        except Exception as e:
            logger.error(f"Error adding command role: {e}")
            return False
    
    async def remove_command_role(self, guild_id: int, command_name: str, role_id: int):
        """Remove a role from command permissions"""
        try:
            settings = await self.storage.get_server_settings(guild_id)
            command_roles = settings.get("command_roles", {}).get(command_name, [])
            
            if role_id in command_roles:
                settings["command_roles"][command_name].remove(role_id)
                await self.storage.update_server_settings(guild_id, settings)
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing command role: {e}")
            return False
    
    async def get_command_roles(self, guild_id: int, command_name: str) -> List[int]:
        """Get roles that have permission for a command"""
        try:
            settings = await self.storage.get_server_settings(guild_id)
            return settings.get("command_roles", {}).get(command_name, [])
        except Exception as e:
            logger.error(f"Error getting command roles: {e}")
            return []