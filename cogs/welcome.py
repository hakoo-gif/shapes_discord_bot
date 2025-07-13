import discord
from discord.ext import commands
from discord import app_commands
import logging
import aiohttp
import json
from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class WelcomeCog(commands.Cog):
    """Welcome message management cog"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
        self.shapes_api_url = "https://api.shapes.inc/v1/chat/completions"
        
        # Fallback welcome messages when API fails
        self.fallback_messages = [
            "Welcome to {server_name}, {mention}! 🎉 We're glad to have you here!",
            "Hey there {mention}! Welcome to {server_name}! Hope you enjoy your stay!",
            "Welcome {mention}! Great to have you join us in {server_name}!",
            "Hello {mention}! Welcome to our awesome community {server_name}!",
            "Welcome aboard {mention}! Thanks for joining {server_name}!",
            "Hey {mention}! Welcome to {server_name}! Looking forward to chatting with you!",
            "Welcome {mention}! {server_name} just got a little more awesome!",
            "Hi {mention}! Welcome to {server_name}! Hope you have a great time here!",
            "Welcome {mention}! So excited to have you in {server_name}!",
            "Hey there {mention}! Welcome to the {server_name} family!"
        ]
    
    @app_commands.command(name="welcome", description="Configure welcome messages for new members")
    @app_commands.describe(
        channel="The channel to send welcome messages to",
        status="Enable or disable welcome messages"
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="Enable", value="enable"),
        app_commands.Choice(name="Disable", value="disable")
    ])
    async def welcome(self, interaction: discord.Interaction, channel: discord.TextChannel, status: str):
        """Configure welcome messages"""
        try:
            # Check permissions
            has_permission, error_message = await self.permission_manager.check_permission(
                interaction.user, "welcome", PermissionLevel.ADMIN
            )
            
            if not has_permission:
                await interaction.response.send_message(error_message, ephemeral=True)
                return
            
            # Check if bot has permissions in the target channel
            bot_member = interaction.guild.get_member(self.bot.user.id)
            if not bot_member:
                await interaction.response.send_message("❌ Bot member not found in guild.", ephemeral=True)
                return
            
            channel_permissions = channel.permissions_for(bot_member)
            if not (channel_permissions.send_messages and channel_permissions.view_channel):
                await interaction.response.send_message(
                    f"❌ I don't have permission to send messages in {channel.mention}. "
                    f"Please ensure I have 'Send Messages' and 'View Channel' permissions.",
                    ephemeral=True
                )
                return
            
            # Update welcome settings
            await self.bot.storage.set_welcome_settings(
                interaction.guild.id,
                enabled=(status == "enable"),
                channel_id=channel.id if status == "enable" else None
            )
            
            if status == "enable":
                embed = discord.Embed(
                    title="✅ Welcome Messages Enabled",
                    description=f"Welcome messages will be sent to {channel.mention} when new members join.",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="❌ Welcome Messages Disabled",
                    description="Welcome messages have been disabled for this server.",
                    color=discord.Color.red()
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in welcome command: {e}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while configuring welcome messages.",
                ephemeral=True
            )
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle new member joins"""
        try:
            # Get welcome settings
            welcome_settings = await self.bot.storage.get_welcome_settings(member.guild.id)
            
            if not welcome_settings.get('enabled', False):
                return
            
            channel_id = welcome_settings.get('channel_id')
            if not channel_id:
                return
            
            channel = member.guild.get_channel(channel_id)
            if not channel:
                logger.warning(f"Welcome channel {channel_id} not found in guild {member.guild.id}")
                return
            
            # Check bot permissions
            bot_member = member.guild.get_member(self.bot.user.id)
            if not bot_member:
                return
            
            channel_permissions = channel.permissions_for(bot_member)
            if not (channel_permissions.send_messages and channel_permissions.view_channel):
                logger.warning(f"No permission to send welcome message in channel {channel_id}")
                return
            
            # Generate welcome message
            welcome_message = await self._generate_welcome_message(member)
            
            if welcome_message:
                try:
                    await channel.send(welcome_message)
                except discord.Forbidden:
                    logger.warning(f"Failed to send welcome message in {channel_id} - permission denied")
                except discord.HTTPException as e:
                    logger.error(f"Failed to send welcome message: {e}")
            
        except Exception as e:
            logger.error(f"Error handling member join: {e}", exc_info=True)
    
    async def _generate_welcome_message(self, member: discord.Member) -> str:
        """Generate a welcome message using Shapes API"""
        try:
            # Check if Shapes API key is available
            if not hasattr(self.bot, 'shapes_api_key') or not self.bot.shapes_api_key:
                logger.error("Shapes API key not found")
                return self._get_fallback_message(member)
            
            # Load persona from persona.txt
            persona = ""
            try:
                with open('persona.txt', 'r', encoding='utf-8') as f:
                    persona = f.read().strip()
            except FileNotFoundError:
                logger.warning("persona.txt not found, using default personality")
                persona = "You are a friendly and welcoming Discord bot."
            except Exception as e:
                logger.error(f"Error reading persona.txt: {e}")
                persona = "You are a friendly and welcoming Discord bot."
            
            # Create prompt for welcome message
            prompt = f"""{persona}

Generate a welcome message for a new member who just joined a Discord server.

Server name: {member.guild.name}
New member: {member.display_name}
Member count: {member.guild.member_count}

Requirements:
- Keep it natural and welcoming, maintaining your personality
- Make it feel personal but not too long
- Include the member's name, you can skip server name and member count if you want
- Keep it under 200 characters
- Don't mention any specific rules or channels
- Stay true to your personality while being welcoming
- Don't include the member mention (@) in your response, that will be added automatically

Generate a single welcome message only, no additional text or explanations."""
            
            # Prepare messages for the API
            messages = [{"role": "user", "content": prompt}]
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.bot.shapes_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": f"shapesinc/{self.bot.SHAPES_USERNAME}",
                "messages": messages
            }
            
            # Make API request with timeout and retry logic
            max_retries = 3
            retry_delay = 1
            
            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                        async with session.post(self.shapes_api_url, json=payload, headers=headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                if 'choices' in data and len(data['choices']) > 0:
                                    content = data['choices'][0]['message']['content'].strip()
                                    # Remove any quotes that might wrap the response
                                    content = content.strip('"\'')
                                    if content:
                                        # Add mention to the generated message
                                        return f"{content} {member.mention}"
                            elif response.status == 429:
                                # Rate limited
                                if attempt < max_retries - 1:
                                    logger.warning(f"Rate limited, retrying in {retry_delay} seconds (attempt {attempt + 1})")
                                    await asyncio.sleep(retry_delay)
                                    retry_delay *= 2  # Exponential backoff
                                    continue
                                else:
                                    logger.warning("Rate limited on final attempt, using fallback")
                                    break
                            else:
                                logger.warning(f"Shapes API returned status {response.status}")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(retry_delay)
                                    retry_delay *= 2
                                    continue
                                break
                                
                except aiohttp.ClientError as e:
                    logger.error(f"HTTP error generating welcome message (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    break
                except Exception as e:
                    logger.error(f"Unexpected error generating welcome message (attempt {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    break
            
        except Exception as e:
            logger.error(f"Error in _generate_welcome_message: {e}", exc_info=True)
        
        # Fallback to random message if API fails
        return self._get_fallback_message(member)
    
    def _get_fallback_message(self, member: discord.Member) -> str:
        """Get a fallback welcome message"""
        import random
        
        # Choose a random fallback message and format it
        template = random.choice(self.fallback_messages)
        return template.format(
            server_name=member.guild.name,
            mention=member.mention
        )

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(WelcomeCog(bot))
