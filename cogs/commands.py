import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List
from utils.auth import AuthManager
import os
import uuid

logger = logging.getLogger(__name__)

class CommandsCog(commands.Cog):
    """Slash commands for bot configuration and management"""
    
    def __init__(self, bot):
        self.bot = bot
        self.auth_manager = AuthManager(bot.storage, os.getenv('SHAPES_APP_ID', ''))
    
    def _has_admin_permissions(self, member: discord.Member) -> bool:
        """Check if member has administrator or manage server permissions"""
        return member.guild_permissions.administrator or member.guild_permissions.manage_guild
    
    def _is_bot_owner(self, user_id: int) -> bool:
        """Check if user is the bot owner"""
        return user_id == self.bot.bot_owner_id
    
    @app_commands.command(name="activate", description="Enable or disable auto respond in this channel")
    @app_commands.describe(enabled="Enable or disable the bot")
    async def activate(self, interaction: discord.Interaction, enabled: bool):
        """Enable or disable auto respond in the channel"""
        try:
            # Check permissions
            if not self._has_admin_permissions(interaction.user):
                await interaction.response.send_message(
                    "❌ You need Administrator or Manage Server permissions to use this command.",
                    ephemeral=True
                )
                return
            
            # Update server settings
            await self.bot.storage.set_server_activation(interaction.guild.id, enabled)
            
            status = "enabled" if enabled else "disabled"
            embed = discord.Embed(
                title="✅ Bot Status Updated",
                description=f"Bot has been **{status}** in this server.",
                color=discord.Color.green() if enabled else discord.Color.red()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in activate command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating bot status.",
                ephemeral=True
            )
    
    @app_commands.command(name="blacklist", description="Manage channel blacklist")
    async def blacklist(self, interaction: discord.Interaction):
        """Manage channel blacklist"""
        try:
            # Check permissions
            if not self._has_admin_permissions(interaction.user):
                await interaction.response.send_message(
                    "❌ You need Administrator or Manage Server permissions to use this command.",
                    ephemeral=True
                )
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
            if not self._has_admin_permissions(interaction.user):
                await interaction.response.send_message(
                    "❌ You need Administrator or Manage Server permissions to use this command.",
                    ephemeral=True
                )
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
    
    @app_commands.command(name="block", description="Block or unblock a user")
    @app_commands.describe(
        user="The user to block/unblock",
        action="Block or unblock the user"  
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Block", value="block"),
        app_commands.Choice(name="Unblock", value="unblock")
    ])
    async def block(self, interaction: discord.Interaction, user: discord.Member, 
                    action: app_commands.Choice[str]):
        """Block or unblock a user"""
        try:
            # Check permissions (admin or manage server, plus optional bot owner)
            has_admin_perms = self._has_admin_permissions(interaction.user)
            is_owner = (hasattr(self.bot, 'bot_owner_id') and 
                       self.bot.bot_owner_id is not None and 
                       self._is_bot_owner(interaction.user.id))
            
            if not (has_admin_perms or is_owner):
                if hasattr(self.bot, 'bot_owner_id') and self.bot.bot_owner_id is not None:
                    error_msg = "❌ You need to be the bot owner, Administrator, or have Manage Server permissions to use this command."
                else:
                    error_msg = "❌ You need Administrator or Manage Server permissions to use this command."
                
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            # Can't block/unblock self or bot
            if user.id == interaction.user.id:
                await interaction.response.send_message(
                    "❌ You cannot block/unblock yourself.",
                    ephemeral=True
                )
                return
            
            if user.id == self.bot.user.id:
                await interaction.response.send_message(
                    "❌ You cannot block/unblock the bot itself.",
                    ephemeral=True
                )
                return
            
            # Perform action
            if action.value == "block":
                await self.bot.storage.block_user(interaction.guild.id, user.id)
                embed = discord.Embed(
                    title="🚫 User Blocked",
                    description=f"**{user.display_name}** has been blocked in this server.\nThe bot will ignore all messages from this user.",
                    color=discord.Color.red()
                )
            else:
                await self.bot.storage.unblock_user(interaction.guild.id, user.id)
                embed = discord.Embed(
                    title="✅ User Unblocked",
                    description=f"**{user.display_name}** has been unblocked in this server.\nThe bot will now respond to this user normally.",
                    color=discord.Color.green()
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in block command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing user block status.",
                ephemeral=True
            )
    
    @app_commands.command(name="auth", description="Authenticate with Shapes API or remove authentication")
    @app_commands.describe(action="Choose to authenticate or remove authentication")
    @app_commands.choices(action=[
        app_commands.Choice(name="Authenticate", value="auth"),
        app_commands.Choice(name="Remove Authentication", value="deauth")
    ])
    async def auth(self, interaction: discord.Interaction, action: Optional[app_commands.Choice[str]] = None):
        """Show authentication interface or remove authentication"""
        try:
            # If no action specified or action is auth, show authentication interface
            if action is None or action.value == "auth":
                embed = discord.Embed(
                    title="🔐 Shapes API Authentication",
                    description="Authenticate with your Shapes API credentials to use your personal profile and rate limits.",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Step 1: Get your App ID",
                    value="1. Go to [shapes.inc/developer](https://shapes.inc/developer)\n"
                          "2. Create an API key with type **APPLICATION**\n"
                          "3. Copy your **App ID** (save your API key somewhere safe too!)\n"
                          "4. Click the **App ID** button below to enter it",
                    inline=False
                )
                
                embed.add_field(
                    name="Step 2: Authorize",
                    value="After entering your App ID, you'll get an authorization link.\n"
                          "Visit the link and copy the code you receive.\n"
                          "Then click the **Code** button to complete authentication.",
                    inline=False
                )
                
                view = AuthView(self.auth_manager, interaction.user.id)
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
            elif action.value == "deauth":
                # Remove authentication
                success = await self.auth_manager.remove_user_auth_token(interaction.user.id)
                
                if success:
                    embed = discord.Embed(
                        title="✅ Authentication Removed",
                        description="Your Shapes API authentication has been successfully removed.\n"
                                   "You can authenticate again anytime using `/auth`.",
                        color=discord.Color.green()
                    )
                else:
                    embed = discord.Embed(
                        title="ℹ️ No Authentication Found",
                        description="You don't currently have any authentication stored.\n"
                                   "Use `/auth` to authenticate with Shapes API.",
                        color=discord.Color.blue()
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in auth command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing authentication.",
                ephemeral=True
            )

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
        
        # Split channels into chunks of 25 (Discord limit)
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
            for channel in channels[:25]  # Discord limit
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
                    title="✅ Channel Added",
                    description=f"**#{channel.name}** has been added to the {self.list_type}.",
                    color=discord.Color.green()
                )
            else:
                if self.list_type == "blacklist":
                    await self.bot.storage.remove_from_blacklist(interaction.guild.id, channel_id)
                else:
                    await self.bot.storage.remove_from_whitelist(interaction.guild.id, channel_id)
                
                embed = discord.Embed(
                    title="✅ Channel Removed",
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

class AuthView(discord.ui.View):
    """View for authentication process"""
    
    def __init__(self, auth_manager: AuthManager, user_id: int):
        super().__init__(timeout=600)  # 10 minutes timeout
        self.auth_manager = auth_manager
        self.user_id = user_id
        self.app_id = None
    
    @discord.ui.button(label="App ID", style=discord.ButtonStyle.primary, emoji="🔑")
    async def app_id_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle App ID input"""
        try:
            await interaction.response.send_modal(AppIDModal(self))
        except Exception as e:
            logger.error(f"Error showing App ID modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while showing the App ID form.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Code", style=discord.ButtonStyle.secondary, emoji="🎫", disabled=True)
    async def code_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle authorization code input"""
        try:
            if not self.app_id:
                await interaction.response.send_message(
                    "❌ Please enter your App ID first!",
                    ephemeral=True
                )
                return
            
            await interaction.response.send_modal(AuthCodeModal(self))
        except Exception as e:
            logger.error(f"Error showing auth code modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while showing the authorization code form.",
                ephemeral=True
            )
    
    async def set_app_id(self, app_id: str):
        """Set the app ID and enable code button"""
        self.app_id = app_id
        # Enable the code button
        for item in self.children:
            if hasattr(item, 'label') and item.label == "Code":
                item.disabled = False
                break

class AppIDModal(discord.ui.Modal):
    """Modal for App ID input"""
    
    def __init__(self, auth_view: AuthView):
        super().__init__(title="Enter Your Shapes App ID")
        self.auth_view = auth_view
        
        self.app_id_input = discord.ui.TextInput(
            label="App ID",
            placeholder="Enter your Shapes App ID here...",
            max_length=100,
            required=True
        )
        self.add_item(self.app_id_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            app_id = self.app_id_input.value.strip()
            
            if not app_id:
                await interaction.response.send_message(
                    "❌ App ID cannot be empty!",
                    ephemeral=True
                )
                return
            
            # Validate UUID format
            try:
                uuid_obj = uuid.UUID(app_id, version=4)
                if str(uuid_obj) != app_id:
                    raise ValueError("Invalid UUID format")
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid App ID format! Please make sure it's a valid UUID **(XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX)**.",
                    ephemeral=True
                )
                return
            
            # Store app ID temporarily
            await self.auth_view.set_app_id(app_id)
            
            # Generate auth URL
            auth_url = f"https://shapes.inc/authorize?app_id={app_id}"
            
            embed = discord.Embed(
                title="🔗 Authorization Required",
                description=f"Click the link below to authorize:\n"
                           f"[Authorize with Shapes]({auth_url})\n\n"
                           f"After authorization, you'll receive a code. Click the **Code** button to enter it.",
                color=discord.Color.green()
            )
            
            # Update the view to enable the code button
            await interaction.response.edit_message(embed=embed, view=self.auth_view)
            
        except Exception as e:
            logger.error(f"Error in App ID modal submit: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing your App ID.",
                ephemeral=True
            )

class AuthCodeModal(discord.ui.Modal):
    """Modal for authorization code input"""
    
    def __init__(self, auth_view: AuthView):
        super().__init__(title="Enter Authorization Code")
        self.auth_view = auth_view
        
        self.code_input = discord.ui.TextInput(
            label="Authorization Code",
            placeholder="Paste the authorization code you received...",
            max_length=200,
            required=True
        )
        self.add_item(self.code_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            code = self.code_input.value.strip()
            
            if not code:
                await interaction.response.send_message(
                    "❌ Authorization code cannot be empty!",
                    ephemeral=True
                )
                return
            
            # Show loading message
            await interaction.response.send_message(
                "⏳ Processing your authorization...",
                ephemeral=True
            )
            
            # Exchange code for token
            success = await self.auth_view.auth_manager.exchange_code(
                self.auth_view.user_id, 
                code,
                self.auth_view.app_id
            )
            
            if success:
                embed = discord.Embed(
                    title="✅ Authentication Successful!",
                    description="You have successfully authenticated.",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Authentication Failed",
                    description="The authorization code you provided is invalid or expired.\n\n"
                               "Please try again with a new code:\n"
                               "1. Visit the authorization link again\n"
                               "2. Get a new code\n"
                               "3. Use the `/auth` command again",
                    color=discord.Color.red()
                )
            
            # Edit the original response
            await interaction.edit_original_response(content=None, embed=embed)
            
        except Exception as e:
            logger.error(f"Error in auth code modal submit: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing your authorization code.",
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(CommandsCog(bot))
