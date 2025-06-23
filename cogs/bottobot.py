import discord
from discord.ext import commands
from discord import app_commands
import logging

from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class BotToBotCog(commands.Cog):
    """Cog for managing bot-to-bot conversation settings"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
    
    @app_commands.command(
        name="botchat",
        description="Enable or disable bot-to-bot conversations in this channel"
    )
    @app_commands.describe(
        enabled="Whether to enable bot-to-bot conversations in this channel"
    )
    async def botchat(self, interaction: discord.Interaction, enabled: bool):
        """Enable or disable bot-to-bot conversations in the current channel"""
        try:
            # Check if command is used in DM
            if not interaction.guild:
                await interaction.response.send_message(
                    "❌ This command can only be used in servers.", 
                    ephemeral=True
                )
                return
            
            # Check permissions
            has_permission, error_msg = await self.permission_manager.check_permission(
                interaction.user, "botchat", PermissionLevel.ADMIN
            )
            
            if not has_permission:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            # Update bot-to-bot setting for this channel
            await self.bot.storage.set_bot_to_bot_enabled(
                interaction.guild.id, 
                interaction.channel.id, 
                enabled
            )
            
            # Send confirmation message
            status = "enabled" if enabled else "disabled"
            embed = discord.Embed(
                color=discord.Color.green() if enabled else discord.Color.red(),
                title="Bot-to-Bot Conversations",
                description=f"Bot-to-bot conversations have been **{status}** in {interaction.channel.mention}."
            )
            
            if enabled:
                embed.add_field(
                    name="ℹ️ Note",
                    value="The bot will now respond to messages from other bots in this channel.",
                    inline=False
                )
            else:
                embed.add_field(
                    name="ℹ️ Note", 
                    value="The bot will no longer respond to messages from other bots in this channel.",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
            # logger.info(f"Bot-to-bot conversations {status} in channel {interaction.channel.id} by user {interaction.user.id}")
            
        except Exception as e:
            logger.error(f"Error in botchat command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while updating the bot-to-bot setting.", 
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(BotToBotCog(bot))
