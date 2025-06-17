import discord
from discord.ext import commands
from discord import app_commands
import logging
from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class TriggerCommand(commands.Cog):
    """Server-specific trigger word management"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
    
    @app_commands.command(name="trigger", description="Add, remove, or list server-specific trigger words")
    @app_commands.describe(
        action="Add, remove, or list trigger words",
        word="The trigger word to add or remove (use quotes for phrases with spaces)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="List", value="list")
    ])
    async def trigger(self, interaction: discord.Interaction, action: str, word: str = None):
        """Manage server-specific trigger words"""
        try:
            # Check permissions - server owner > admin > selected roles
            has_permission, error_msg = await self.permission_manager.check_permission(
                interaction.user, "trigger", PermissionLevel.SELECTED_ROLES
            )
            
            if not has_permission:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return
            
            if action == "list":
                # List current server trigger words
                trigger_words = await self.bot.storage.get_server_trigger_words(interaction.guild.id)
                
                if not trigger_words:
                    embed = discord.Embed(
                        title="Server Trigger Words",
                        description="No custom trigger words set for this server.\nThe bot will still respond to global trigger words and mentions.",
                        color=discord.Color.blue()
                    )
                else:
                    # Format trigger words list with proper formatting
                    formatted_words = [f"`{word}`" for word in trigger_words]
                    words_text = ", ".join(formatted_words)
                    
                    # Split into multiple embeds if too long
                    if len(words_text) > 2000:
                        words_chunks = []
                        current_chunk = []
                        current_length = 0
                        
                        for word in formatted_words:
                            if current_length + len(word) + 2 > 1900:  # Leave room for formatting
                                words_chunks.append(", ".join(current_chunk))
                                current_chunk = [word]
                                current_length = len(word)
                            else:
                                current_chunk.append(word)
                                current_length += len(word) + 2
                        
                        if current_chunk:
                            words_chunks.append(", ".join(current_chunk))
                        
                        # Send first chunk
                        embed = discord.Embed(
                            title="Server Trigger Words (Part 1)",
                            description=words_chunks[0],
                            color=discord.Color.blue()
                        )
                        embed.set_footer(text=f"Total: {len(trigger_words)} words")
                        await interaction.response.send_message(embed=embed, ephemeral=False)
                        
                        # Send remaining chunks
                        for i, chunk in enumerate(words_chunks[1:], 2):
                            embed = discord.Embed(
                                title=f"Server Trigger Words (Part {i})",
                                description=chunk,
                                color=discord.Color.blue()
                            )
                            await interaction.followup.send(embed=embed, ephemeral=False)
                        
                        return
                    else:
                        embed = discord.Embed(
                            title="Server Trigger Words",
                            description=words_text,
                            color=discord.Color.blue()
                        )
                        embed.set_footer(text=f"Total: {len(trigger_words)} words")
                
                await interaction.response.send_message(embed=embed, ephemeral=False)
                return
            
            # For add/remove actions, word is required
            if not word:
                await interaction.response.send_message(
                    "❌ Please specify a trigger word for add/remove actions.",
                    ephemeral=True
                )
                return
            
            # Clean and validate the word
            word = word.strip().lower()
            
            if not word:
                await interaction.response.send_message(
                    "❌ Trigger word cannot be empty.",
                    ephemeral=True
                )
                return
            
            if len(word) > 100:
                await interaction.response.send_message(
                    "❌ Trigger word cannot be longer than 100 characters.",
                    ephemeral=True
                )
                return
            
            if action == "add":
                success = await self.bot.storage.add_server_trigger_word(interaction.guild.id, word)
                
                if success:
                    embed = discord.Embed(
                        title="Trigger Word Added",
                        description=f"✅ Added `{word}` to server trigger words.\nThe bot will now respond when this word is mentioned.",
                        color=discord.Color.green()
                    )
                else:
                    embed = discord.Embed(
                        title="Trigger Word Not Added",
                        description=f"⚠️ `{word}` is already a trigger word for this server.",
                        color=discord.Color.orange()
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=False)
            
            elif action == "remove":
                success = await self.bot.storage.remove_server_trigger_word(interaction.guild.id, word)
                
                if success:
                    embed = discord.Embed(
                        title="Trigger Word Removed",
                        description=f"✅ Removed `{word}` from server trigger words.\nThe bot will no longer respond to this word (unless it's a global trigger word).",
                        color=discord.Color.red()
                    )
                else:
                    embed = discord.Embed(
                        title="Trigger Word Not Removed",
                        description=f"⚠️ `{word}` was not found in server trigger words.",
                        color=discord.Color.orange()
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=False)
            
        except Exception as e:
            logger.error(f"Error in trigger command: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while managing trigger words.",
                ephemeral=True
            )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(TriggerCommand(bot))