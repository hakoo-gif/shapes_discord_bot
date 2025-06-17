import discord
from discord.ext import commands
from discord import app_commands
import logging
from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class ActivateCommand(commands.Cog):
    """Channel-specific activation command"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
    
    @app_commands.command(name="activate", description="Enable or disable auto respond in this specific channel")
    @app_commands.describe(enabled="Enable or disable the bot in this channel")
    async def activate(self, interaction: discord.Interaction, enabled: bool):
        """Enable or disable auto respond in the specific channel"""
        try:
            # Check permissions
            has_permission, error_msg = await self.permission_manager.check_permission(
                interaction.user, "activate", PermissionLevel.ADMIN
            )
            
            if not has_permission:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            # Update channel-specific settings
            await self.bot.storage.set_channel_activation(
                interaction.guild.id, 
                interaction.channel.id, 
                enabled
            )
            
            status = "enabled" if enabled else "disabled"
            behavior = (
                "The bot will now respond to all messages in this channel, but will avoid joining conversations between other users (unless mentioned or triggered)."
                if enabled else
                "The bot will only respond when mentioned or triggered in this channel."
            )
            
            embed = discord.Embed(
                title="Channel Activation Updated",
                description=f"Bot has been **{status}** in {interaction.channel.mention}.\n\n{behavior}",
                color=discord.Color.green() if enabled else discord.Color.red()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
        except Exception as e:
            logger.error(f"Error in activate command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while updating channel status.",
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ActivateCommand(bot))