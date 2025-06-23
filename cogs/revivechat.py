import json
import random
import asyncio
import logging
import aiohttp
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.permissions import PermissionManager, PermissionLevel

logger = logging.getLogger(__name__)

class ReviveChatCog(commands.Cog):
    """Revive chat functionality with scheduled messages"""
    
    def __init__(self, bot):
        self.bot = bot
        self.permission_manager = PermissionManager(bot, bot.storage)
        self.shapes_api_url = "https://api.shapes.inc/v1/chat/completions"
        
        # Fallback messages when API fails
        self.fallback_messages = [
            "What's everyone up to today? Let's get this chat moving!",
            "Anyone have any interesting stories to share?",
            "What's the most exciting thing that happened to you this week?",
            "If you could have dinner with anyone, dead or alive, who would it be and why?",
            "What's your go-to comfort food when you're having a rough day?",
            "Share something you learned recently that surprised you!",
            "What's a skill you'd love to master if you had unlimited time?",
            "Describe your perfect weekend in three words.",
            "What's the best advice you've ever received?",
            "If you could travel anywhere right now, where would you go?",
            "What's something you're looking forward to this month?",
            "Share a random fact that most people don't know!",
            "What's your favorite way to unwind after a long day?",
            "If you could have any superpower for just one day, what would it be?",
            "What's the most beautiful place you've ever visited?",
            "Share something that always makes you smile!",
            "What's a hobby you've always wanted to try?",
            "Describe the last thing that made you laugh out loud.",
            "What's your favorite season and why?",
            "If you could master any language instantly, which would you choose?"
        ]
        
        # Active schedulers
        self.active_schedulers: Dict[str, asyncio.Task] = {}
        
        # Start the scheduler checker
        self.scheduler_checker.start()
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.scheduler_checker.cancel()
        for task in self.active_schedulers.values():
            task.cancel()
    
    @tasks.loop(minutes=1)
    async def scheduler_checker(self):
        """Check and restart schedulers after bot restart"""
        try:
            # Get all guilds and check their revive chat settings
            for guild in self.bot.guilds:
                server_settings = await self.bot.storage.get_server_settings(guild.id)
                settings = server_settings.get('revive_chat', {})

                if settings.get('enabled', False):
                    scheduler_key = f"{guild.id}_{settings.get('channel_id', 0)}"
                    
                    # If scheduler isn't running, start it
                    if scheduler_key not in self.active_schedulers:
                        await self._start_scheduler(
                            guild.id,
                            settings['channel_id'],
                            settings['role_id'],
                            settings['interval_minutes'],
                            settings.get('next_send_time')
                        )
        except Exception as e:
            logger.error(f"Error in scheduler checker: {e}")
    
    @scheduler_checker.before_loop
    async def before_scheduler_checker(self):
        """Wait for bot to be ready before starting scheduler checker"""
        await self.bot.wait_until_ready()
    
    def _parse_time_format(self, time_str: str) -> Optional[int]:
        """
        Parse time format like '1h', '2h15m', '30m' into minutes
        Max 24 hours (1440 minutes)
        """
        try:
            time_str = time_str.lower().strip()
            
            # Pattern to match formats like: 1h, 2h15m, 30m, 1h30m
            pattern = r'^(?:(\d+)h)?(?:(\d+)m)?$'
            match = re.match(pattern, time_str)
            
            if not match:
                return None
            
            hours = int(match.group(1)) if match.group(1) else 0
            minutes = int(match.group(2)) if match.group(2) else 0
            
            # Validate input
            if hours == 0 and minutes == 0:
                return None
            
            if hours > 24:
                return None
            
            total_minutes = hours * 60 + minutes
            
            # Max 24 hours (1440 minutes), min 1 minute
            if total_minutes > 1440 or total_minutes < 1:
                return None
            
            return total_minutes
            
        except Exception as e:
            logger.error(f"Error parsing time format '{time_str}': {e}")
            return None
    
    def _format_time_display(self, minutes: int) -> str:
        """Convert minutes back to display format"""
        hours = minutes // 60
        mins = minutes % 60
        
        if hours > 0 and mins > 0:
            return f"{hours}h{mins}m"
        elif hours > 0:
            return f"{hours}h"
        else:
            return f"{mins}m"
    
    async def _generate_revive_message(self, guild_id: int) -> str:
        """Generate revive chat message using AI or fallback"""
        try:
            # Prepare prompt for AI
            prompt = "Chat’s dead. Say one short, natural line (in your tone) that could spark someone to reply — not like a mod or QOTD."
            
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
            
            # Make API request with timeout
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(self.shapes_api_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'choices' in data and len(data['choices']) > 0:
                            content = data['choices'][0]['message']['content'].strip()
                            # Remove any quotes that might wrap the response
                            content = content.strip('"\'')
                            if content:
                                return content
                    elif response.status == 429:
                        # Rate limited, will retry later
                        logger.warning(f"Rate limited when generating revive message for guild {guild_id}")
                        raise aiohttp.ClientResponseError(response.request_info, response.history, status=429)
                    else:
                        logger.warning(f"API returned status {response.status} for revive message generation")
            
        except aiohttp.ClientResponseError as e:
            if e.status == 429:
                # Rate limited, re-raise to handle in scheduler
                raise
            else:
                logger.error(f"API error generating revive message: {e}")
        except Exception as e:
            logger.error(f"Error generating revive message: {e}")
        
        # Fallback to random message
        return random.choice(self.fallback_messages)
    
    async def _send_revive_message(self, guild_id: int, channel_id: int, role_id: int):
        """Send a revive chat message"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"Guild {guild_id} not found for revive chat")
                return False
            
            channel = guild.get_channel(channel_id)
            if not channel:
                logger.error(f"Channel {channel_id} not found in guild {guild_id}")
                return False
            
            role = guild.get_role(role_id)
            if not role:
                logger.error(f"Role {role_id} not found in guild {guild_id}")
                return False
            
            # Check bot permissions
            bot_member = guild.get_member(self.bot.user.id)
            if not bot_member:
                logger.error(f"Bot not found in guild {guild_id}")
                return False
            
            permissions = channel.permissions_for(bot_member)
            if not (permissions.send_messages and permissions.view_channel):
                logger.error(f"Missing permissions in channel {channel_id}")
                return False
            
            # Generate message with retry logic for rate limits
            max_retries = 3
            retry_delay = 60
            
            for attempt in range(max_retries):
                try:
                    message_content = await self._generate_revive_message(guild_id)
                    break
                except aiohttp.ClientResponseError as e:
                    if e.status == 429 and attempt < max_retries - 1:
                        logger.info(f"Rate limited, retrying in {retry_delay} seconds (attempt {attempt + 1})")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        # Use fallback on final attempt or non-rate-limit errors
                        message_content = random.choice(self.fallback_messages)
                        break
                except Exception:
                    # Use fallback for any other error
                    message_content = random.choice(self.fallback_messages)
                    break
            
            # Send message with role ping
            final_message = f"{message_content} {role.mention}"
            
            await channel.send(final_message)
            logger.info(f"Sent revive chat message to {guild.name} #{channel.name}")
            return True
            
        except discord.Forbidden:
            logger.error(f"Permission denied sending revive message to channel {channel_id}")
            return False
        except Exception as e:
            logger.error(f"Error sending revive message: {e}")
            return False
    
    async def _start_scheduler(self, guild_id: int, channel_id: int, role_id: int, 
                             interval_minutes: int, next_send_time: Optional[str] = None):
        """Start the scheduler for a guild"""
        scheduler_key = f"{guild_id}_{channel_id}"
        
        # Cancel existing scheduler if any
        if scheduler_key in self.active_schedulers:
            self.active_schedulers[scheduler_key].cancel()
        
        # Create and start new scheduler task
        task = asyncio.create_task(
            self._scheduler_loop(guild_id, channel_id, role_id, interval_minutes, next_send_time)
        )
        self.active_schedulers[scheduler_key] = task
        
        logger.info(f"Started revive chat scheduler for guild {guild_id}, channel {channel_id}")
    
    async def _scheduler_loop(self, guild_id: int, channel_id: int, role_id: int, 
                            interval_minutes: int, next_send_time: Optional[str] = None):
        """Main scheduler loop"""
        try:
            # Calculate first send time
            if next_send_time:
                try:
                    next_time = datetime.fromisoformat(next_send_time)
                    if next_time <= datetime.now():
                        # Time has passed, send immediately and calculate next
                        next_time = datetime.now()
                except ValueError:
                    next_time = datetime.now()
            else:
                next_time = datetime.now()
            
            while True:
                # Check if still enabled
                server_settings = await self.bot.storage.get_server_settings(guild_id)
                settings = server_settings.get('revive_chat', {})

                if not settings.get('enabled', False):
                    logger.info(f"Revive chat disabled for guild {guild_id}, stopping scheduler")
                    break
                
                # Wait until next send time
                now = datetime.now()
                if next_time > now:
                    sleep_seconds = (next_time - now).total_seconds()
                    logger.debug(f"Sleeping {sleep_seconds} seconds until next revive message")
                    await asyncio.sleep(sleep_seconds)
                
                # Send message
                success = await self._send_revive_message(guild_id, channel_id, role_id)
                
                # Calculate next send time
                next_time = datetime.now() + timedelta(minutes=interval_minutes)
                
                # Update next send time in storage
                server_settings = await self.bot.storage.get_server_settings(guild_id)
                if 'revive_chat' not in server_settings:
                    server_settings['revive_chat'] = {}
                server_settings['revive_chat']['next_send_time'] = next_time.isoformat()
                await self.bot.storage.update_server_settings(guild_id, server_settings)
                
                logger.info(f"Next revive message for guild {guild_id} scheduled for {next_time}")
                
        except asyncio.CancelledError:
            logger.info(f"Revive chat scheduler cancelled for guild {guild_id}")
        except Exception as e:
            logger.error(f"Error in revive chat scheduler for guild {guild_id}: {e}")
        finally:
            # Clean up scheduler reference
            scheduler_key = f"{guild_id}_{channel_id}"
            if scheduler_key in self.active_schedulers:
                del self.active_schedulers[scheduler_key]
    
    @app_commands.command(name="revivechat", description="Manage automated revive chat messages")
    @app_commands.describe(
        action="Action to perform",
        channel="Channel to send revive messages (required for enable)",
        role="Role to ping in revive messages (required for enable)", 
        interval="Time interval (e.g., '1h', '2h30m', '45m') - max 24h (required for enable)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="enable", value="enable"),
        app_commands.Choice(name="disable", value="disable"),
        app_commands.Choice(name="status", value="status")
    ])
    async def revivechat(self, interaction: discord.Interaction, action: str,
                        channel: Optional[discord.TextChannel] = None,
                        role: Optional[discord.Role] = None,
                        interval: Optional[str] = None):
        """Revive chat command"""
        
        # Check permissions
        if not interaction.guild:
            embed = discord.Embed(
                title="❌ Error",
                description="This command can only be used in servers.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        has_permission, error_message = await self.permission_manager.check_permission(
        interaction.user, "revivechat", PermissionLevel.ADMIN
        )
        
        if not has_permission:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description=error_message,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            if action == "enable":
                # Validate required parameters
                if not channel:
                    embed = discord.Embed(
                        title="❌ Missing Parameter",
                        description="Channel parameter is required for enabling revive chat.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                if not role:
                    embed = discord.Embed(
                        title="❌ Missing Parameter",
                        description="Role parameter is required for enabling revive chat.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                if not interval:
                    embed = discord.Embed(
                        title="❌ Missing Parameter",
                        description="Interval parameter is required for enabling revive chat.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Parse interval
                interval_minutes = self._parse_time_format(interval)
                if interval_minutes is None:
                    embed = discord.Embed(
                        title="❌ Invalid Time Format",
                        description="Use formats like `1h`, `2h30m`, or `45m`. Maximum 24 hours.",
                        color=discord.Color.red()
                    )
                    embed.add_field(
                        name="Examples",
                        value="`30m` - 30 minutes\n`1h` - 1 hour\n`2h15m` - 2 hours 15 minutes",
                        inline=False
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Check bot permissions in target channel
                bot_member = interaction.guild.get_member(self.bot.user.id)
                if not bot_member:
                    embed = discord.Embed(
                        title="❌ Bot Error",
                        description="Bot member not found in guild.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                permissions = channel.permissions_for(bot_member)
                if not (permissions.send_messages and permissions.view_channel):
                    embed = discord.Embed(
                        title="❌ Missing Permissions",
                        description=f"I don't have permission to send messages in {channel.mention}.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Check if role is mentionable or bot has 'Mention @everyone, @here, and All Roles' permission
                warning_message = None
                if not role.mentionable and not bot_member.guild_permissions.mention_everyone:
                    warning_message = f"⚠️ **Warning:** Role {role.mention} is not mentionable and I don't have the 'Mention @everyone, @here, and All Roles' permission. The role ping may not work as expected."
                
                # Save settings
                server_settings = await self.bot.storage.get_server_settings(interaction.guild.id)
                server_settings['revive_chat'] = {
                    'enabled': True,
                    'channel_id': channel.id,
                    'role_id': role.id,
                    'interval_minutes': interval_minutes,
                    'next_send_time': None
                }
                
                await self.bot.storage.update_server_settings(interaction.guild.id, server_settings)
                
                # Start scheduler
                await self._start_scheduler(
                    interaction.guild.id,
                    channel.id,
                    role.id,
                    interval_minutes
                )
                
                interval_display = self._format_time_display(interval_minutes)
                embed = discord.Embed(
                    title="✅ Revive Chat Enabled",
                    description="Automated revive messages have been successfully configured!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Channel", value=channel.mention, inline=True)
                embed.add_field(name="Role", value=role.mention, inline=True)
                embed.add_field(name="Interval", value=interval_display, inline=True)
                
                # Warning if role mention might not work
                if warning_message:
                    embed.add_field(name="⚠️ Notice", value=warning_message, inline=False)
                    embed.color = discord.Color.orange()
                
                embed.set_footer(text=f"Configured by {interaction.user.display_name}")
                embed.timestamp = datetime.now()
                
                await interaction.response.send_message(embed=embed)
            
            elif action == "disable":
                # Get current settings
                server_settings = await self.bot.storage.get_server_settings(interaction.guild.id)
                settings = server_settings.get('revive_chat', {})
                
                if not settings.get('enabled', False):
                    embed = discord.Embed(
                        title="❌ Already Disabled",
                        description="Revive chat is not currently enabled.",
                        color=discord.Color.orange()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Disable in storage
                server_settings['revive_chat'] = settings
                server_settings['revive_chat']['enabled'] = False
                await self.bot.storage.update_server_settings(interaction.guild.id, server_settings)
                
                # Stop scheduler
                scheduler_key = f"{interaction.guild.id}_{settings.get('channel_id', 0)}"
                if scheduler_key in self.active_schedulers:
                    self.active_schedulers[scheduler_key].cancel()
                    del self.active_schedulers[scheduler_key]
                
                embed = discord.Embed(
                    title="Revive Chat Disabled",
                    description="Automated revive messages have been stopped.",
                    color=discord.Color.red()
                )
                embed.set_footer(text=f"Disabled by {interaction.user.display_name}")
                embed.timestamp = datetime.now()
                
                await interaction.response.send_message(embed=embed)
            
            elif action == "status":
                # Get current settings
                server_settings = await self.bot.storage.get_server_settings(interaction.guild.id)
                settings = server_settings.get('revive_chat', {})
                
                if not settings.get('enabled', False):
                    embed = discord.Embed(
                        title="Revive Chat Status",
                        description="**Status:** Disabled",
                        color=discord.Color.light_grey()
                    )
                    embed.add_field(
                        name="💡 Tip",
                        value="Use `/revivechat enable` to set up automated messages",
                        inline=False
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                # Get channel and role info
                channel = interaction.guild.get_channel(settings.get('channel_id'))
                role = interaction.guild.get_role(settings.get('role_id'))
                
                channel_mention = channel.mention if channel else f"<#{settings.get('channel_id')} (deleted)>"
                role_mention = role.mention if role else f"<@&{settings.get('role_id')}> (deleted)"
                
                interval_display = self._format_time_display(settings.get('interval_minutes', 60))
                
                # Calculate next send time
                next_send_str = "Soon"
                if settings.get('next_send_time'):
                    try:
                        next_time = datetime.fromisoformat(settings['next_send_time'])
                        now = datetime.now()
                        if next_time > now:
                            delta = next_time - now
                            hours, remainder = divmod(delta.total_seconds(), 3600)
                            minutes, _ = divmod(remainder, 60)
                            if hours > 0:
                                next_send_str = f"in {int(hours)}h {int(minutes)}m"
                            else:
                                next_send_str = f"in {int(minutes)}m"
                        else:
                            next_send_str = "Overdue (will send soon)"
                    except ValueError:
                        pass
                
                # Check if scheduler is running
                scheduler_key = f"{interaction.guild.id}_{settings.get('channel_id', 0)}"
                scheduler_running = scheduler_key in self.active_schedulers
                scheduler_status = "🟢 Running" if scheduler_running else "🔴 Not running"
                
                embed = discord.Embed(
                    title="Revive Chat Status",
                    description="**Status:** Enabled",
                    color=discord.Color.green() if scheduler_running else discord.Color.orange()
                )
                embed.add_field(name="Channel", value=channel_mention, inline=True)
                embed.add_field(name="Role", value=role_mention, inline=True)
                embed.add_field(name="Interval", value=interval_display, inline=True)
                embed.add_field(name="Next Message", value=next_send_str, inline=True)
                embed.add_field(name="Scheduler", value=scheduler_status, inline=True)
                embed.add_field(name="⚡", value="", inline=True)
                
                if not scheduler_running:
                    embed.add_field(
                        name="⚠️ Notice",
                        value="Scheduler is not running. The bot may have restarted recently.",
                        inline=False
                    )
                
                embed.set_footer(text=f"Requested by {interaction.user.display_name}")
                embed.timestamp = datetime.now()
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in revivechat command: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Unexpected Error",
                description="An error occurred while processing the command. Please try again later.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Support",
                value="If this issue persists, please contact the bot administrator.",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ReviveChatCog(bot))
