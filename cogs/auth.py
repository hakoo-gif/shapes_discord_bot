import discord
from discord.ext import commands
from discord import app_commands
import logging
import uuid
import os
from typing import Optional
from utils.auth import AuthManager
from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class AuthCommand(commands.Cog):
    """Authentication command for Shapes API"""
    
    def __init__(self, bot):
        self.bot = bot
        self.auth_manager = AuthManager(bot.storage, os.getenv('SHAPES_APP_ID', ''))
        self.permission_manager = PermissionManager(bot, bot.storage)
    
    @app_commands.command(name="auth", description="Authenticate with Shapes API or remove authentication")
    @app_commands.describe(action="Choose to authenticate or remove authentication")
    @app_commands.choices(action=[
        app_commands.Choice(name="Authenticate", value="auth"),
        app_commands.Choice(name="Remove Authentication", value="deauth")
    ])
    async def auth(self, interaction: discord.Interaction, action: Optional[app_commands.Choice[str]] = None):
        """Show authentication interface or remove authentication"""
        try:
            # Auth command is available to everyone
            has_permission, error_msg = await self.permission_manager.check_permission(
                interaction.user, "auth", PermissionLevel.EVERYONE
            )
            
            if not has_permission:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
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
            
class AuthView(discord.ui.View):
    """View for authentication process"""
    
    def __init__(self, auth_manager: AuthManager, user_id: int):
        super().__init__(timeout=600)
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
                    "❌ Invalid App ID format! Please make sure it's a valid UUID **`XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`**.",
                    ephemeral=True
                )
                return
            
            # Store App ID temporarily
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
            
            await interaction.edit_original_response(content=None, embed=embed)
            
        except Exception as e:
            logger.error(f"Error in auth code modal submit: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing your authorization code.",
                ephemeral=True
            )
            
async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(AuthCommand(bot))