import discord
from discord.ext import commands
from discord import app_commands
import logging
from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class PermissionCommand(commands.Cog):
    """Command role management for bot commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
    
    @app_commands.command(name="permission", description="Add or remove roles that can use specific bot commands")
    @app_commands.describe(
        action="Add or remove a role",
        command_name="Name of the command to modify permissions for",
        role="The role to add or remove"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="List", value="list")
    ])
    async def permission(self, interaction: discord.Interaction, action: str, command_name: str, role: discord.Role = None):
        """Add or remove roles that can use specific bot commands"""
        try:
            # Check permissions - only server owner or admin can use this
            has_permission, error_msg = await self.permission_manager.check_permission(
                interaction.user, "permission", PermissionLevel.ADMIN
            )
            
            if not has_permission:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            # Valid command names that can have role permissions
            valid_commands = [
                "activate", "block", "whitelist", "blacklist", "trigger", "revivechat"  # Add more commands as needed
            ]
            
            if command_name not in valid_commands:
                await interaction.response.send_message(
                    f"❌ Invalid command name. Valid commands: {', '.join(valid_commands)}",
                    ephemeral=True
                )
                return
            
            if action == "list":
                # List current roles for the command
                role_ids = await self.permission_manager.get_command_roles(interaction.guild.id, command_name)
                
                if not role_ids:
                    embed = discord.Embed(
                        title=f"Permissions for `/{command_name}`",
                        description="No specific roles have permission for this command.\nServer owner and administrators can always use it.",
                        color=discord.Color.blue()
                    )
                else:
                    role_mentions = []
                    for role_id in role_ids:
                        role_obj = interaction.guild.get_role(role_id)
                        if role_obj:
                            role_mentions.append(role_obj.mention)
                        else:
                            role_mentions.append(f"<Deleted Role: {role_id}>")
                    
                    embed = discord.Embed(
                        title=f"Permissions for `/{command_name}`",
                        description=f"**Authorized Roles:**\n{chr(10).join(role_mentions)}\n\n*Server owner and administrators can always use this command.*",
                        color=discord.Color.blue()
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=False)
                return
            
            # For add/remove actions, role is required
            if role is None:
                await interaction.response.send_message(
                    "❌ Please specify a role for add/remove actions.",
                    ephemeral=True
                )
                return
            
            if action == "add":
                success = await self.permission_manager.add_command_role(
                    interaction.guild.id, command_name, role.id
                )
                
                if success:
                    embed = discord.Embed(
                        title="Permission Added",
                        description=f"✅ {role.mention} can now use `/{command_name}`",
                        color=discord.Color.green()
                    )
                else:
                    embed = discord.Embed(
                        title="Permission Not Changed",
                        description=f"⚠️ {role.mention} already has permission to use `/{command_name}`",
                        color=discord.Color.orange()
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=False)
            
            elif action == "remove":
                success = await self.permission_manager.remove_command_role(
                    interaction.guild.id, command_name, role.id
                )
                
                if success:
                    embed = discord.Embed(
                        title="Permission Removed",
                        description=f"✅ {role.mention} can no longer use `/{command_name}`",
                        color=discord.Color.red()
                    )
                else:
                    embed = discord.Embed(
                        title="Permission Not Changed",
                        description=f"⚠️ {role.mention} didn't have permission to use `/{command_name}`",
                        color=discord.Color.orange()
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=False)
            
        except Exception as e:
            logger.error(f"Error in permission command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing permissions.",
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(PermissionCommand(bot))