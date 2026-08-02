import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import datetime

DATA_FILE = "data/logs.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


class Logs(commands.Cog, name="logs"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

    def get_log_channel(self, guild_id):
        gid = str(guild_id)
        ch_id = self.data.get(gid)
        if ch_id:
            guild = self.bot.get_guild(guild_id)
            if guild:
                return guild.get_channel(ch_id)
        return None

    async def send_log(self, guild_id, embed):
        ch = self.get_log_channel(guild_id)
        if ch:
            await ch.send(embed=embed)

    async def _setlogchannel(self, ctx, channel):
        if channel is None:
            return await ctx.send("Please specify a channel.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        self.data[gid] = channel.id
        save_data(self.data)
        embed = discord.Embed(title="Log Channel Set", description=f"Logs will be sent to {channel.mention}.", color=discord.Color.green())
        if isinstance(ctx, commands.Context):
            await ctx.send(embed=embed)
        else:
            if not ctx.response.is_done():
                await ctx.response.send_message(embed=embed)
            else:
                await ctx.followup.send(embed=embed)

    @commands.command(name="setlogchannel")
    @commands.has_permissions(administrator=True)
    async def setlogchannel_prefix(self, ctx, channel: discord.TextChannel = None):
        await self._setlogchannel(ctx, channel)

    @app_commands.command(name="setlogchannel", description="Set the logging channel")
    @app_commands.default_permissions(administrator=True)
    async def setlogchannel_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._setlogchannel(interaction, channel)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        embed = discord.Embed(title="Member Joined", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member} ({member.id})")
        embed.add_field(name="Created", value=discord.utils.format_dt(member.created_at, style="R"))
        embed.add_field(name="Members", value=member.guild.member_count)
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        embed = discord.Embed(title="Member Left", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member} ({member.id})")
        embed.add_field(name="Joined", value=discord.utils.format_dt(member.joined_at, style="R") if member.joined_at else "Unknown")
        embed.add_field(name="Members", value=member.guild.member_count)
        await self.send_log(member.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        embed = discord.Embed(title="Member Banned", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.add_field(name="User", value=f"{user} ({user.id})")
        async for entry in guild.bans():
            if entry.user.id == user.id:
                embed.add_field(name="Reason", value=entry.reason or "No reason")
                break
        await self.send_log(guild.id, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        embed = discord.Embed(title="Member Unbanned", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="User", value=f"{user} ({user.id})")
        await self.send_log(guild.id, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="Message Edited", color=discord.Color.yellow(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Author", value=before.author.mention)
        embed.add_field(name="Channel", value=before.channel.mention)
        embed.add_field(name="Before", value=before.content[:500], inline=False)
        embed.add_field(name="After", value=after.content[:500], inline=False)
        embed.set_footer(text=f"User ID: {before.author.id}")
        await self.send_log(before.guild.id, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return
        embed = discord.Embed(title="Message Deleted", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Author", value=message.author.mention)
        embed.add_field(name="Channel", value=message.channel.mention)
        if message.content:
            embed.add_field(name="Content", value=message.content[:500], inline=False)
        embed.set_footer(text=f"User ID: {message.author.id}")
        await self.send_log(message.guild.id, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            added = [r.mention for r in after.roles if r not in before.roles]
            removed = [r.mention for r in before.roles if r not in after.roles]
            if added or removed:
                embed = discord.Embed(title="Roles Updated", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
                embed.add_field(name="Member", value=after.mention)
                if added:
                    embed.add_field(name="Added", value=", ".join(added), inline=False)
                if removed:
                    embed.add_field(name="Removed", value=", ".join(removed), inline=False)
                embed.set_footer(text=f"ID: {after.id}")
                await self.send_log(after.guild.id, embed)
        if before.nick != after.nick:
            embed = discord.Embed(title="Nickname Changed", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
            embed.add_field(name="Member", value=after.mention)
            embed.add_field(name="Before", value=before.nick or after.name)
            embed.add_field(name="After", value=after.nick or after.name)
            await self.send_log(after.guild.id, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return
        embed = discord.Embed(title="Voice Update", color=discord.Color.purple(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Member", value=member.mention)
        if before.channel and after.channel:
            embed.add_field(name="Moved", value=f"{before.channel.mention} -> {after.channel.mention}")
        elif before.channel:
            embed.add_field(name="Left", value=before.channel.mention)
            embed.add_field(name="Duration", value=self._voice_duration(before))
        elif after.channel:
            embed.add_field(name="Joined", value=after.channel.mention)
        await self.send_log(member.guild.id, embed)

    def _voice_duration(self, state):
        return "Unknown"

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed = discord.Embed(title="Channel Created", color=discord.Color.green(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Name", value=channel.mention)
        embed.add_field(name="Type", value=str(channel.type).capitalize())
        await self.send_log(channel.guild.id, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed = discord.Embed(title="Channel Deleted", color=discord.Color.red(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Name", value=channel.name)
        embed.add_field(name="Type", value=str(channel.type).capitalize())
        await self.send_log(channel.guild.id, embed)


async def setup(bot):
    await bot.add_cog(Logs(bot))
