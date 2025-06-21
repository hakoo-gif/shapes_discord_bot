import discord
from discord.ext import commands
from discord import app_commands
import logging
from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class SayCog(commands.Cog):
    """Say command cog for sending messages through the bot"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
    
    @app_commands.command(name="say", description="Make the bot say a message")
    @app_commands.describe(
        message="The message to send",
        channel="The channel to send the message to (optional, defaults to current channel)"
    )
    async def say(self, interaction: discord.Interaction, message: str, channel: discord.TextChannel = None):
        """Make the bot say a message"""
        try:
            # Check permissions
            has_permission, error_message = await self.permission_manager.check_permission(
                interaction.user, "say", PermissionLevel.ADMIN
            )
            
            if not has_permission:
                await interaction.response.send_message(error_message, ephemeral=True)
                return
            
            # Determine target channel
            target_channel = channel if channel else interaction.channel
            
            # Check if bot has permissions in the target channel
            bot_member = interaction.guild.get_member(self.bot.user.id) if interaction.guild else None
            
            if interaction.guild and bot_member:
                channel_permissions = target_channel.permissions_for(bot_member)
                if not (channel_permissions.send_messages and channel_permissions.view_channel):
                    await interaction.response.send_message(
                        f"❌ I don't have permission to send messages in {target_channel.mention}. "
                        f"Please ensure I have 'Send Messages' and 'View Channel' permissions.",
                        ephemeral=True
                    )
                    return
            
            # Validate message content
            if not message.strip():
                await interaction.response.send_message("❌ Message cannot be empty.", ephemeral=True)
                return
            
            # Check message length
            if len(message) > 2000:
                await interaction.response.send_message(
                    "❌ Message is too long. Discord messages must be 2000 characters or less.",
                    ephemeral=True
                )
                return
            
            # Send the message
            try:
                await target_channel.send(message)
                
                # Confirm to the user
                if target_channel == interaction.channel:
                    confirmation = "✅ Message sent!"
                else:
                    confirmation = f"✅ Message sent to {target_channel.mention}!"
                
                await interaction.response.send_message(confirmation, ephemeral=True)
                
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"❌ I don't have permission to send messages in {target_channel.mention}.",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                logger.error(f"Failed to send message: {e}")
                await interaction.response.send_message(
                    "❌ Failed to send message due to a Discord error.",
                    ephemeral=True
                )
            
        except Exception as e:
            logger.error(f"Error in say command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while sending the message.",
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(SayCog(bot))
