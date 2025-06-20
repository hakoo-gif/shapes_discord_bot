import discord
from discord.ext import commands
from discord import app_commands
import logging
from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class BlockCommand(commands.Cog):
    """User blocking and unblocking commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
    
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
            # Check permissions - Bot owner > Server owner > Admin > Selected roles
            has_permission = False
            error_msg = ""
            
            if self.permission_manager.is_bot_owner(interaction.user.id):
                has_permission = True
            elif self.permission_manager.is_server_owner(interaction.user):
                has_permission = True
            elif self.permission_manager.has_admin_permissions(interaction.user):
                has_permission = True
            elif await self.permission_manager.has_selected_role_permissions(interaction.user, "block"):
                has_permission = True
            else:
                error_msg = self.permission_manager._get_permission_error_message("block")
            
            if not has_permission:
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

            if self.permission_manager.is_bot_owner(user.id):
                await interaction.response.send_message(
                    "❌ You cannot block/unblock the bot owner.",
                    ephemeral=True
                )
                return
            
            # Server owners can't be blocked by non-bot owners
            if (self.permission_manager.is_server_owner(user) and 
                not self.permission_manager.is_bot_owner(interaction.user.id)):
                await interaction.response.send_message(
                    "❌ You cannot block/unblock the server owner.",
                    ephemeral=True
                )
                return
            
            if action.value == "block":
                await self.bot.storage.block_user(interaction.guild.id, user.id)
                embed = discord.Embed(
                    title="User Blocked",
                    description=f"**{user.display_name}** has been blocked in this server.\nThe bot will ignore all messages from this user.",
                    color=discord.Color.red()
                )
            else:
                await self.bot.storage.unblock_user(interaction.guild.id, user.id)
                embed = discord.Embed(
                    title="User Unblocked",
                    description=f"**{user.display_name}** has been unblocked in this server.\nThe bot will now respond to this user normally.",
                    color=discord.Color.green()
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in block command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing user block status.",
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(BlockCommand(bot))