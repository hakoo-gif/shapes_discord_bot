import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List
from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class ChannelManagementCommand(commands.Cog):
    """Channel whitelist and blacklist management commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
    
    @app_commands.command(name="blacklist", description="Manage channel blacklist")
    async def blacklist(self, interaction: discord.Interaction):
        """Manage channel blacklist"""
        try:
            # Check permissions
            has_permission, error_msg = await self.permission_manager.check_permission(
                interaction.user, "blacklist", PermissionLevel.ADMIN
            )
            
            if not has_permission:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            await self._show_channel_management(interaction, "blacklist")
            
        except Exception as e:
            logger.error(f"Error in blacklist command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing blacklist.",
                ephemeral=True
            )
    
    @app_commands.command(name="whitelist", description="Manage channel whitelist")
    async def whitelist(self, interaction: discord.Interaction):
        """Manage channel whitelist"""
        try:
            # Check permissions
            has_permission, error_msg = await self.permission_manager.check_permission(
                interaction.user, "whitelist", PermissionLevel.ADMIN
            )
            
            if not has_permission:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            await self._show_channel_management(interaction, "whitelist")
            
        except Exception as e:
            logger.error(f"Error in whitelist command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing whitelist.",
                ephemeral=True
            )
    
    async def _show_channel_management(self, interaction: discord.Interaction, list_type: str):
        """Show channel management interface"""
        settings = await self.bot.storage.get_server_settings(interaction.guild.id)
        
        # Get current list
        current_list = settings.get(list_type, [])
        use_blacklist = settings.get("use_blacklist", False)
        opposite_list = settings.get("whitelist" if list_type == "blacklist" else "blacklist", [])
        
        # Create embed
        embed = discord.Embed(
            title=f"📋 Channel {list_type.capitalize()} Management",
            color=discord.Color.blue()
        )
        
        # Show current mode
        current_mode = "Blacklist" if use_blacklist else "Whitelist"
        embed.add_field(
            name="Current Mode",
            value=f"**{current_mode}**",
            inline=True
        )
        
        # Show warning if trying to manage opposite mode
        if (list_type == "blacklist" and not use_blacklist) or (list_type == "whitelist" and use_blacklist):
            embed.add_field(
                name="⚠️ Mode Conflict",
                value=f"You're currently using **{current_mode}** mode.\n"
                      f"Adding channels to {list_type} will switch to **{list_type.capitalize()}** mode "
                      f"and clear the current {current_mode.lower()} list.",
                inline=False
            )
        
        # Show current channels
        if current_list:
            channel_mentions = []
            for channel_id in current_list:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    channel_mentions.append(channel.mention)
                else:
                    channel_mentions.append(f"<#{channel_id}> (deleted)")
            
            embed.add_field(
                name=f"Current {list_type.capitalize()}",
                value="\n".join(channel_mentions) if channel_mentions else "None",
                inline=False
            )
        else:
            embed.add_field(
                name=f"Current {list_type.capitalize()}",
                value="None",
                inline=False
            )
        
        # Show opposite list if it has channels (will be cleared when switching)
        if opposite_list:
            opposite_name = "Whitelist" if list_type == "blacklist" else "Blacklist"
            opposite_mentions = []
            for channel_id in opposite_list:
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    opposite_mentions.append(channel.mention)
                else:
                    opposite_mentions.append(f"<#{channel_id}> (deleted)")
            
            embed.add_field(
                name=f"Current {opposite_name} (will be cleared)",
                value="\n".join(opposite_mentions),
                inline=False
            )
        
        # Add explanation
        if list_type == "blacklist":
            embed.add_field(
                name="ℹ️ Blacklist Mode",
                value="Bot will **ignore** channels in the blacklist and respond in all other channels.",
                inline=False
            )
        else:
            embed.add_field(
                name="ℹ️ Whitelist Mode", 
                value="Bot will **only respond** in channels in the whitelist.",
                inline=False
            )
        
        # Create dropdown for action selection
        view = ChannelManagementView(self.bot, list_type)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ChannelManagementView(discord.ui.View):
    """View for managing channel blacklist/whitelist"""
    
    def __init__(self, bot, list_type: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.list_type = list_type
        
        # Add action dropdown
        self.add_item(ActionDropdown(bot, list_type))

class ActionDropdown(discord.ui.Select):
    """Dropdown for selecting add/remove action"""
    
    def __init__(self, bot, list_type: str):
        self.bot = bot
        self.list_type = list_type
        
        options = [
            discord.SelectOption(
                label="Add Channel",
                description=f"Add a channel to the {list_type}",
                value="add"
            ),
            discord.SelectOption(
                label="Remove Channel", 
                description=f"Remove a channel from the {list_type}",
                value="remove"
            )
        ]
        
        super().__init__(
            placeholder=f"Choose an action for {list_type}...",
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            action = self.values[0]
            
            # Get current settings
            settings = await self.bot.storage.get_server_settings(interaction.guild.id)
            current_list = settings.get(self.list_type, [])
            
            # Create channel selection dropdown
            if action == "add":
                # Show channels not in the list
                available_channels = [
                    ch for ch in interaction.guild.text_channels 
                    if ch.id not in current_list
                ]
            else:
                # Show channels in the list
                available_channels = [
                    ch for ch in interaction.guild.text_channels 
                    if ch.id in current_list
                ]
            
            if not available_channels:
                message = "No channels available to add." if action == "add" else "No channels to remove."
                await interaction.response.send_message(f"❌ {message}", ephemeral=True)
                return
            
            # Create new view with channel dropdown
            view = ChannelSelectionView(self.bot, self.list_type, action, available_channels)
            
            embed = discord.Embed(
                title=f"📋 {action.capitalize()} Channel - {self.list_type.capitalize()}",
                description=f"Select a channel to {action}:",
                color=discord.Color.blue()
            )
            
            await interaction.response.edit_message(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error in action dropdown callback: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing your selection.",
                ephemeral=True
            )

class ChannelSelectionView(discord.ui.View):
    """View for selecting channels to add/remove"""
    
    def __init__(self, bot, list_type: str, action: str, channels: List[discord.TextChannel]):
        super().__init__(timeout=300)
        self.bot = bot
        self.list_type = list_type
        self.action = action
        
        # Split channels into chunks of 25
        channel_chunks = [channels[i:i+25] for i in range(0, len(channels), 25)]
        
        for i, chunk in enumerate(channel_chunks):
            dropdown = ChannelDropdown(bot, list_type, action, chunk, i)
            self.add_item(dropdown)

class ChannelDropdown(discord.ui.Select):
    """Dropdown for selecting specific channels"""
    
    def __init__(self, bot, list_type: str, action: str, channels: List[discord.TextChannel], chunk_index: int):
        self.bot = bot
        self.list_type = list_type
        self.action = action
        
        options = [
            discord.SelectOption(
                label=f"#{channel.name}",
                description=f"{channel.category.name if channel.category else 'No Category'}",
                value=str(channel.id)
            )
            for channel in channels[:25]
        ]
        
        placeholder = f"Select channel to {action}..."
        if chunk_index > 0:
            placeholder += f" (Group {chunk_index + 1})"
        
        super().__init__(
            placeholder=placeholder,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.values[0])
            channel = interaction.guild.get_channel(channel_id)
            
            if not channel:
                await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
                return
            
            # Perform action
            if self.action == "add":
                if self.list_type == "blacklist":
                    await self.bot.storage.add_to_blacklist(interaction.guild.id, channel_id)
                else:
                    await self.bot.storage.add_to_whitelist(interaction.guild.id, channel_id)
                
                embed = discord.Embed(
                    title="Channel Added",
                    description=f"**#{channel.name}** has been added to the {self.list_type}.",
                    color=discord.Color.green()
                )
            else:
                if self.list_type == "blacklist":
                    await self.bot.storage.remove_from_blacklist(interaction.guild.id, channel_id)
                else:
                    await self.bot.storage.remove_from_whitelist(interaction.guild.id, channel_id)
                
                embed = discord.Embed(
                    title="Channel Removed",
                    description=f"**#{channel.name}** has been removed from the {self.list_type}.",
                    color=discord.Color.green()
                )
            
            await interaction.response.edit_message(embed=embed, view=None)
            
        except Exception as e:
            logger.error(f"Error in channel dropdown callback: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating the channel list.",
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ChannelManagementCommand(bot))