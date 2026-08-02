import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
import os

DATA_FILE = "data/moderation.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"warnings": {}, "mutes": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


async def respond(ctx_or_interaction, embed=None, content=None, ephemeral=False):
    if isinstance(ctx_or_interaction, commands.Context):
        await ctx_or_interaction.send(embed=embed, content=content)
    else:
        if not ctx_or_interaction.response.is_done():
            await ctx_or_interaction.response.send_message(embed=embed, content=content, ephemeral=ephemeral)
        else:
            await ctx_or_interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral)


class Moderation(commands.Cog, name="moderation"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

    # --- KICK ---
    async def _kick(self, ctx, member, reason):
        if member is None:
            return await respond(ctx, content="Please specify a member to kick.")
        if member == ctx.author if isinstance(ctx, commands.Context) else ctx.user:
            return await respond(ctx, content="You can't kick yourself.")
        guild = ctx.guild if isinstance(ctx, commands.Context) else ctx.guild
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        if member.top_role >= author.top_role and author != guild.owner:
            return await respond(ctx, content="You can't kick someone with a higher or equal role.")
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(title="Member Kicked", color=discord.Color.orange())
            embed.add_field(name="Member", value=f"{member} ({member.id})")
            embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Moderator", value=author.mention)
            await respond(ctx, embed=embed)
            try:
                await member.send(f"You were kicked from **{guild.name}**.\nReason: {reason}")
            except:
                pass
        except discord.Forbidden:
            await respond(ctx, content="I don't have permission to kick that member.")

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick_prefix(self, ctx, member: discord.Member = None, *, reason="No reason provided"):
        await self._kick(ctx, member, reason)

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.default_permissions(kick_members=True)
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await self._kick(interaction, member, reason)

    # --- BAN ---
    async def _ban(self, ctx, member, delete_days, reason):
        if member is None:
            return await respond(ctx, content="Please specify a member to ban.")
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        guild = ctx.guild if isinstance(ctx, commands.Context) else ctx.guild
        if member == author:
            return await respond(ctx, content="You can't ban yourself.")
        if member.top_role >= author.top_role and author != guild.owner:
            return await respond(ctx, content="You can't ban someone with a higher or equal role.")
        try:
            await member.ban(reason=reason, delete_message_days=delete_days)
            embed = discord.Embed(title="Member Banned", color=discord.Color.red())
            embed.add_field(name="Member", value=f"{member} ({member.id})")
            embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Moderator", value=author.mention)
            await respond(ctx, embed=embed)
        except discord.Forbidden:
            await respond(ctx, content="I don't have permission to ban that member.")

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban_prefix(self, ctx, member: discord.Member = None, delete_days: int = 0, *, reason="No reason provided"):
        await self._ban(ctx, member, delete_days, reason)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.default_permissions(ban_members=True)
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member, delete_days: app_commands.Range[int, 0, 7] = 0, reason: str = "No reason provided"):
        await self._ban(interaction, member, delete_days, reason)

    # --- UNBAN ---
    async def _unban(self, ctx, user_input):
        guild = ctx.guild if isinstance(ctx, commands.Context) else ctx.guild
        banned_users = [entry async for entry in guild.bans()]
        for entry in banned_users:
            if str(entry.user) == user_input or str(entry.user.id) == user_input:
                await guild.unban(entry.user)
                embed = discord.Embed(title="Member Unbanned", color=discord.Color.green())
                embed.add_field(name="User", value=f"{entry.user} ({entry.user.id})")
                return await respond(ctx, embed=embed)
        await respond(ctx, content=f"User `{user_input}` not found in bans.")

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    async def unban_prefix(self, ctx, *, user_input):
        await self._unban(ctx, user_input)

    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.default_permissions(ban_members=True)
    async def unban_slash(self, interaction: discord.Interaction, user_id: str):
        await self._unban(interaction, user_id)

    # --- MUTE ---
    async def _mute(self, ctx, member, duration_min, reason):
        if member is None:
            return await respond(ctx, content="Please specify a member to mute.")
        guild = ctx.guild if isinstance(ctx, commands.Context) else ctx.guild
        mute_role = discord.utils.get(guild.roles, name="Muted")
        if not mute_role:
            mute_role = await guild.create_role(name="Muted", reason="Auto-created mute role")
            for channel in guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, speak=False)
        await member.add_roles(mute_role, reason=reason)
        expiry = (datetime.datetime.utcnow() + datetime.timedelta(minutes=duration_min)).timestamp()
        uid = str(member.id)
        if uid not in self.data["mutes"]:
            self.data["mutes"][uid] = []
        self.data["mutes"][uid].append({"expiry": expiry, "reason": reason, "mod": ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id})
        save_data(self.data)
        embed = discord.Embed(title="Member Muted", color=discord.Color.orange())
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Duration", value=f"{duration_min} minutes")
        embed.add_field(name="Reason", value=reason)
        await respond(ctx, embed=embed)

    @commands.command(name="mute")
    @commands.has_permissions(manage_roles=True)
    async def mute_prefix(self, ctx, member: discord.Member = None, duration_min: int = 10, *, reason="No reason provided"):
        await self._mute(ctx, member, duration_min, reason)

    @app_commands.command(name="mute", description="Mute a member")
    @app_commands.default_permissions(manage_roles=True)
    async def mute_slash(self, interaction: discord.Interaction, member: discord.Member, duration_min: app_commands.Range[int, 1, 1440] = 10, reason: str = "No reason provided"):
        await self._mute(interaction, member, duration_min, reason)

    # --- UNMUTE ---
    async def _unmute(self, ctx, member):
        if member is None:
            return await respond(ctx, content="Please specify a member to unmute.")
        guild = ctx.guild if isinstance(ctx, commands.Context) else ctx.guild
        mute_role = discord.utils.get(guild.roles, name="Muted")
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role)
            uid = str(member.id)
            if uid in self.data["mutes"]:
                del self.data["mutes"][uid]
                save_data(self.data)
            await respond(ctx, content=f"{member.mention} has been unmuted.")
        else:
            await respond(ctx, content=f"{member.mention} is not muted.")

    @commands.command(name="unmute")
    @commands.has_permissions(manage_roles=True)
    async def unmute_prefix(self, ctx, member: discord.Member = None):
        await self._unmute(ctx, member)

    @app_commands.command(name="unmute", description="Unmute a member")
    @app_commands.default_permissions(manage_roles=True)
    async def unmute_slash(self, interaction: discord.Interaction, member: discord.Member):
        await self._unmute(interaction, member)

    # --- WARN ---
    async def _warn(self, ctx, member, reason):
        if member is None:
            return await respond(ctx, content="Please specify a member to warn.")
        uid = str(member.id)
        if uid not in self.data["warnings"]:
            self.data["warnings"][uid] = []
        warning = {"reason": reason, "mod": ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id, "time": datetime.datetime.utcnow().isoformat()}
        self.data["warnings"][uid].append(warning)
        save_data(self.data)
        embed = discord.Embed(title="Warning Issued", color=discord.Color.yellow())
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Warning #", value=len(self.data["warnings"][uid]))
        embed.add_field(name="Reason", value=reason)
        await respond(ctx, embed=embed)

    @commands.command(name="warn")
    @commands.has_permissions(manage_messages=True)
    async def warn_prefix(self, ctx, member: discord.Member = None, *, reason="No reason provided"):
        await self._warn(ctx, member, reason)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.default_permissions(manage_messages=True)
    async def warn_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await self._warn(interaction, member, reason)

    # --- WARNINGS ---
    async def _warnings(self, ctx, member):
        if member is None:
            return await respond(ctx, content="Please specify a member.")
        uid = str(member.id)
        warns = self.data["warnings"].get(uid, [])
        if not warns:
            return await respond(ctx, content=f"{member.mention} has no warnings.")
        embed = discord.Embed(title=f"Warnings for {member}", color=discord.Color.yellow())
        for i, w in enumerate(warns, 1):
            embed.add_field(name=f"Warning {i}", value=f"Reason: {w['reason']}\n<@{w['mod']}> | {w['time'][:10]}", inline=False)
        await respond(ctx, embed=embed)

    @commands.command(name="warnings")
    @commands.has_permissions(manage_messages=True)
    async def warnings_prefix(self, ctx, member: discord.Member = None):
        await self._warnings(ctx, member)

    @app_commands.command(name="warnings", description="List warnings for a member")
    @app_commands.default_permissions(manage_messages=True)
    async def warnings_slash(self, interaction: discord.Interaction, member: discord.Member):
        await self._warnings(interaction, member)

    # --- CLEARWARNS ---
    @commands.command(name="clearwarns")
    @commands.has_permissions(administrator=True)
    async def clearwarns_prefix(self, ctx, member: discord.Member = None):
        if member is None:
            return await ctx.send("Please specify a member.")
        uid = str(member.id)
        if uid in self.data["warnings"]:
            del self.data["warnings"][uid]
            save_data(self.data)
        await ctx.send(f"Cleared all warnings for {member.mention}.")

    @app_commands.command(name="clearwarns", description="Clear all warnings for a member")
    @app_commands.default_permissions(administrator=True)
    async def clearwarns_slash(self, interaction: discord.Interaction, member: discord.Member):
        uid = str(member.id)
        if uid in self.data["warnings"]:
            del self.data["warnings"][uid]
            save_data(self.data)
        await interaction.response.send_message(f"Cleared all warnings for {member.mention}.", ephemeral=True)

    # --- PURGE ---
    @commands.command(name="purge")
    @commands.has_permissions(manage_messages=True)
    async def purge_prefix(self, ctx, count: int = 10):
        if count < 1 or count > 1000:
            return await ctx.send("Count must be between 1 and 1000.")
        deleted = await ctx.channel.purge(limit=count + 1)
        await ctx.send(f"Deleted {len(deleted) - 1} messages.", delete_after=3)

    @app_commands.command(name="purge", description="Bulk delete messages")
    @app_commands.default_permissions(manage_messages=True)
    async def purge_slash(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 1000] = 10):
        deleted = await interaction.channel.purge(limit=count + 1)
        await interaction.response.send_message(f"Deleted {len(deleted) - 1} messages.", delete_after=3)

    # --- CLEAR ---
    async def _clear(self, ctx, count=10, all_messages=False):
        channel = ctx.channel
        if all_messages:
            deleted = await channel.purge(limit=None)
            msg = f"Deleted {len(deleted)} messages from {channel.mention}."
        else:
            deleted = await channel.purge(limit=count + 1)
            msg = f"Deleted {len(deleted) - 1} messages from {channel.mention}."
        await respond(ctx, content=msg)

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def clear_prefix(self, ctx, count_or_all: str = "10"):
        if count_or_all.lower() == "all":
            return await self._clear(ctx, all_messages=True)
        try:
            count = int(count_or_all)
        except ValueError:
            return await ctx.send("Usage: `!clear <count>` or `!clear all`")
        if count < 1 or count > 1000:
            return await ctx.send("Count must be between 1 and 1000.")
        await self._clear(ctx, count=count)

    @app_commands.command(name="clear", description="Clear messages from this channel")
    @app_commands.default_permissions(manage_messages=True)
    async def clear_slash(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 1000] = 10, all: bool = False):
        await self._clear(interaction, count=count, all_messages=all)

    # --- ROLE ALL ---
    async def _role_all(self, ctx, role, remove=False):
        guild = ctx.guild if isinstance(ctx, commands.Context) else ctx.guild
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        if role is None:
            return await respond(ctx, content="Please specify a role.")
        if role == guild.default_role:
            return await respond(ctx, content="You can't assign the @everyone role to members.")
        if role.managed:
            return await respond(ctx, content="That role is managed by Discord or a bot and can't be assigned manually.")
        if role >= guild.me.top_role:
            return await respond(ctx, content="I can't do that because that role is above or equal to my highest role.")

        action = "removing" if remove else "adding"
        verb = "Removed" if remove else "Added"
        if isinstance(ctx, discord.Interaction):
            await ctx.response.defer()
        progress = await respond(ctx, content=f"{action.capitalize()} **{role.mention}** to all members... this may take a moment.")

        if remove:
            targets = [m for m in guild.members if not m.bot and role in m.roles]
        else:
            targets = [m for m in guild.members if not m.bot and role not in m.roles]

        done = 0
        failed = 0
        for m in targets:
            try:
                if remove:
                    await m.remove_roles(role, reason=f"Mass role removal by {author}")
                else:
                    await m.add_roles(role, reason=f"Mass role assignment by {author}")
                done += 1
            except discord.Forbidden:
                failed += 1
            except Exception:
                failed += 1

        embed = discord.Embed(
            title=f"{verb} Role To All Members",
            color=discord.Color.orange() if remove else discord.Color.green(),
        )
        embed.add_field(name="Role", value=role.mention)
        embed.add_field(name="Members Updated", value=str(done))
        if failed:
            embed.add_field(name="Failed", value=str(failed))
        embed.set_footer(text=f"Requested by {author}")
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send(embed=embed)
        else:
            await respond(ctx, embed=embed)

    @commands.command(name="addroleall")
    @commands.has_permissions(administrator=True)
    async def addroleall_prefix(self, ctx, role: discord.Role = None):
        await self._role_all(ctx, role, remove=False)

    @app_commands.command(name="addroleall", description="Add a role to all members")
    @app_commands.default_permissions(administrator=True)
    async def addroleall_slash(self, interaction: discord.Interaction, role: discord.Role):
        await self._role_all(interaction, role, remove=False)

    @commands.command(name="removeroleall")
    @commands.has_permissions(administrator=True)
    async def removeroleall_prefix(self, ctx, role: discord.Role = None):
        await self._role_all(ctx, role, remove=True)

    @app_commands.command(name="removeroleall", description="Remove a role from all members")
    @app_commands.default_permissions(administrator=True)
    async def removeroleall_slash(self, interaction: discord.Interaction, role: discord.Role):
        await self._role_all(interaction, role, remove=True)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        uid = str(member.id)
        mute_data = self.data.get("mutes", {}).get(uid, [])
        now = datetime.datetime.utcnow().timestamp()
        for m in mute_data:
            if m["expiry"] > now:
                mute_role = discord.utils.get(member.guild.roles, name="Muted")
                if mute_role:
                    await member.add_roles(mute_role)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
