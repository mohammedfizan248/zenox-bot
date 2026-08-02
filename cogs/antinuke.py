import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import time
import datetime

DATA_FILE = "data/antinuke.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
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


DEFAULT_CONFIG = {
    "enabled": False,
    "trusted_roles": [],
    "action": "ban",
    "timeout_minutes": 60,
    "protect_channels": True,
    "protect_roles": True,
    "protect_bans": True,
    "protect_kicks": True,
    "protect_webhooks": True,
    "ban_threshold": 5,
    "ban_window": 10,
    "kick_threshold": 5,
    "kick_window": 10,
}


class AntiNuke(commands.Cog, name="antinuke"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()
        self.ban_times = {}
        self.kick_times = {}

    def config(self, guild_id):
        gid = str(guild_id)
        if gid not in self.data:
            self.data[gid] = dict(DEFAULT_CONFIG)
            save_data(self.data)
        cfg = self.data[gid]
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg

    def is_trusted(self, member):
        if member is None:
            return False
        if member.guild_permissions.administrator:
            return True
        if member.guild_permissions.manage_guild:
            return True
        cfg = self.config(member.guild.id)
        return any(role.id in cfg["trusted_roles"] for role in member.roles)

    async def log_action(self, guild, title, content, color=discord.Color.red()):
        log = self.bot.get_cog("Logs")
        if log:
            embed = discord.Embed(title=title, description=content, color=color, timestamp=discord.utils.utcnow())
            await log.send_log(guild.id, embed)

    async def get_actor(self, guild, action):
        try:
            async for entry in guild.audit_logs(action=action, limit=5):
                if entry.user and not entry.user.bot:
                    return entry.user
        except Exception:
            return None
        return None

    async def punish(self, guild, member, reason):
        cfg = self.config(guild.id)
        action = cfg["action"]
        if action == "ban":
            try:
                await member.ban(reason=f"[Anti-Nuke] {reason}")
            except Exception:
                pass
        elif action == "kick":
            try:
                await member.kick(reason=f"[Anti-Nuke] {reason}")
            except Exception:
                pass
        else:
            try:
                duration = datetime.timedelta(minutes=cfg["timeout_minutes"])
                await member.timeout(discord.utils.utcnow() + duration, reason=f"[Anti-Nuke] {reason}")
            except Exception:
                pass
        await self.log_action(guild, "🛡️ Anti-Nuke Triggered", f"{member.mention} was punished for: {reason}", color=discord.Color.red())

    async def lockdown(self, guild, on):
        for channel in guild.channels:
            try:
                if isinstance(channel, discord.TextChannel):
                    await channel.set_permissions(guild.default_role, send_messages=not on)
            except Exception:
                pass

    # --- COMMANDS ---
    async def _setantinuke(self, ctx, enabled):
        cfg = self.config(ctx.guild.id)
        cfg["enabled"] = enabled
        save_data(self.data)
        await respond(ctx, content=f"Anti-nuke protection is now **{'ON' if enabled else 'OFF'}**.")

    @commands.command(name="antinuke")
    @commands.has_permissions(administrator=True)
    async def antinuke_prefix(self, ctx, enabled: str = None):
        if enabled is None:
            cfg = self.config(ctx.guild.id)
            return await ctx.send(f"Anti-nuke is currently **{'ON' if cfg['enabled'] else 'OFF'}**.")
        await self._setantinuke(ctx, enabled.lower() in ("on", "true", "yes", "1"))

    @app_commands.command(name="antinuke", description="Enable or disable anti-nuke protection")
    @app_commands.default_permissions(administrator=True)
    async def antinuke_slash(self, interaction: discord.Interaction, enabled: bool):
        await self._setantinuke(interaction, enabled)

    async def _antitrust(self, ctx, add, role):
        if role is None:
            return await respond(ctx, content="Please specify a role.")
        cfg = self.config(ctx.guild.id)
        if add:
            if role.id in cfg["trusted_roles"]:
                return await respond(ctx, content=f"{role.mention} is already trusted.")
            cfg["trusted_roles"].append(role.id)
            save_data(self.data)
            await respond(ctx, content=f"{role.mention} added to anti-nuke trusted roles.")
        else:
            if role.id not in cfg["trusted_roles"]:
                return await respond(ctx, content=f"{role.mention} is not trusted.")
            cfg["trusted_roles"].remove(role.id)
            save_data(self.data)
            await respond(ctx, content=f"{role.mention} removed from trusted roles.")

    @commands.command(name="antitrust")
    @commands.has_permissions(administrator=True)
    async def antitrust_prefix(self, ctx, add: str = None, role: discord.Role = None):
        if add is None or role is None:
            return await ctx.send("Usage: `antitrust <add|remove> <role>`")
        await self._antitrust(ctx, add.lower() in ("add", "true", "1"), role)

    @app_commands.command(name="antitrust", description="Add or remove a trusted role for anti-nuke")
    @app_commands.default_permissions(administrator=True)
    async def antitrust_slash(self, interaction: discord.Interaction, action: str, role: discord.Role):
        await self._antitrust(interaction, action.lower() == "add", role)

    async def _antitoggle(self, ctx, feature, enabled):
        cfg = self.config(ctx.guild.id)
        key = {
            "channels": "protect_channels",
            "roles": "protect_roles",
            "bans": "protect_bans",
            "kicks": "protect_kicks",
            "webhooks": "protect_webhooks",
        }.get(feature)
        if not key:
            return await respond(ctx, content="Feature must be one of: channels, roles, bans, kicks, webhooks.")
        cfg[key] = enabled
        save_data(self.data)
        await respond(ctx, content=f"Anti-nuke protection for **{feature}** is now **{'ON' if enabled else 'OFF'}**.")

    @commands.command(name="antitoggle")
    @commands.has_permissions(administrator=True)
    async def antitoggle_prefix(self, ctx, feature: str = None, enabled: str = None):
        if not feature or enabled is None:
            return await ctx.send("Usage: `antitoggle <channels|roles|bans|kicks|webhooks> <on|off>`")
        await self._antitoggle(ctx, feature.lower(), enabled.lower() in ("on", "true", "yes", "1"))

    @app_commands.command(name="antitoggle", description="Toggle a specific anti-nuke protection")
    @app_commands.default_permissions(administrator=True)
    async def antitoggle_slash(self, interaction: discord.Interaction, feature: str, enabled: bool):
        await self._antitoggle(interaction, feature.lower(), enabled)

    async def _antipunish(self, ctx, action):
        if action not in ("ban", "kick", "timeout"):
            return await respond(ctx, content="Action must be `ban`, `kick`, or `timeout`.")
        cfg = self.config(ctx.guild.id)
        cfg["action"] = action
        save_data(self.data)
        await respond(ctx, content=f"Anti-nuke punishment set to **{action}**.")

    @commands.command(name="antipunish")
    @commands.has_permissions(administrator=True)
    async def antipunish_prefix(self, ctx, action: str = None):
        if not action:
            return await ctx.send("Usage: `antipunish <ban|kick|timeout>`")
        await self._antipunish(ctx, action.lower())

    @app_commands.command(name="antipunish", description="Set the anti-nuke punishment action")
    @app_commands.default_permissions(administrator=True)
    async def antipunish_slash(self, interaction: discord.Interaction, action: str):
        await self._antipunish(interaction, action.lower())

    async def _antinukestatus(self, ctx):
        cfg = self.config(ctx.guild.id)
        embed = discord.Embed(title="🛡️ Anti-Nuke Status", color=discord.Color.green())
        embed.add_field(name="Protection", value="ON" if cfg["enabled"] else "OFF")
        embed.add_field(name="Punishment", value=cfg["action"])
        embed.add_field(name="Channels", value="ON" if cfg["protect_channels"] else "OFF")
        embed.add_field(name="Roles", value="ON" if cfg["protect_roles"] else "OFF")
        embed.add_field(name="Bans", value=f"ON ({cfg['ban_threshold']}/{cfg['ban_window']}s)" if cfg["protect_bans"] else "OFF")
        embed.add_field(name="Kicks", value=f"ON ({cfg['kick_threshold']}/{cfg['kick_window']}s)" if cfg["protect_kicks"] else "OFF")
        embed.add_field(name="Webhooks", value="ON" if cfg["protect_webhooks"] else "OFF")
        trusted = ", ".join(f"<@&{r}>" for r in cfg["trusted_roles"]) if cfg["trusted_roles"] else "None"
        embed.add_field(name="Trusted Roles", value=trusted, inline=False)
        await respond(ctx, embed=embed)

    @commands.command(name="antinukestatus")
    @commands.has_permissions(administrator=True)
    async def antinukestatus_prefix(self, ctx):
        await self._antinukestatus(ctx)

    @app_commands.command(name="antinukestatus", description="View anti-nuke settings")
    @app_commands.default_permissions(administrator=True)
    async def antinukestatus_slash(self, interaction: discord.Interaction):
        await self._antinukestatus(interaction)

    # --- LOCKDOWN ---
    async def _lockdown(self, ctx):
        await self.lockdown(ctx.guild, True)
        await self.log_action(ctx.guild, "🔒 Server Locked Down", f"{ctx.author if isinstance(ctx, commands.Context) else ctx.user.mention} locked down the server.")
        await respond(ctx, content="🔒 **Server locked down.** All text channels are now read-only.")

    @commands.command(name="lockdown")
    @commands.has_permissions(administrator=True)
    async def lockdown_prefix(self, ctx):
        await self._lockdown(ctx)

    @app_commands.command(name="lockdown", description="Lock down the server (all channels read-only)")
    @app_commands.default_permissions(administrator=True)
    async def lockdown_slash(self, interaction: discord.Interaction):
        await self._lockdown(interaction)

    async def _unlock(self, ctx):
        await self.lockdown(ctx.guild, False)
        await self.log_action(ctx.guild, "🔓 Server Unlocked", f"{ctx.author if isinstance(ctx, commands.Context) else ctx.user.mention} unlocked the server.", color=discord.Color.green())
        await respond(ctx, content="🔓 **Server unlocked.** Channels are back to normal.")

    @commands.command(name="unlock")
    @commands.has_permissions(administrator=True)
    async def unlock_prefix(self, ctx):
        await self._unlock(ctx)

    @app_commands.command(name="unlock", description="Unlock the server after a lockdown")
    @app_commands.default_permissions(administrator=True)
    async def unlock_slash(self, interaction: discord.Interaction):
        await self._unlock(interaction)

    # --- LISTENERS ---
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        guild = channel.guild
        cfg = self.config(guild.id)
        if not cfg["enabled"] or not cfg["protect_channels"]:
            return
        actor = await self.get_actor(guild, discord.AuditLogAction.channel_delete)
        if actor is None or actor == self.bot.user:
            return
        member = guild.get_member(actor.id)
        if member and self.is_trusted(member):
            return
        try:
            category = guild.get_channel(channel.category_id) if getattr(channel, "category_id", None) else None
            await guild.create_text_channel(channel.name, category=category, reason="[Anti-Nuke] Restored deleted channel")
        except Exception:
            pass
        await self.lockdown(guild, True)
        await self.log_action(guild, "Channel Deleted", f"`#{channel.name}` was deleted by {actor.mention}. Channel restored and server locked down.")
        if member:
            await self.punish(guild, member, "Deleted a channel")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        guild = channel.guild
        cfg = self.config(guild.id)
        if not cfg["enabled"] or not cfg["protect_channels"]:
            return
        actor = await self.get_actor(guild, discord.AuditLogAction.channel_create)
        if actor is None or actor == self.bot.user:
            return
        member = guild.get_member(actor.id)
        if member and self.is_trusted(member):
            return
        try:
            await channel.delete(reason="[Anti-Nuke] Unauthorized channel creation")
        except Exception:
            pass
        await self.log_action(guild, "Channel Created", f"{actor.mention} created `#{channel.name}` without permission. Channel deleted.")
        if member:
            await self.punish(guild, member, "Created a channel without permission")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        guild = role.guild
        cfg = self.config(guild.id)
        if not cfg["enabled"] or not cfg["protect_roles"]:
            return
        actor = await self.get_actor(guild, discord.AuditLogAction.role_delete)
        if actor is None or actor == self.bot.user:
            return
        member = guild.get_member(actor.id)
        if member and self.is_trusted(member):
            return
        try:
            await guild.create_role(name=role.name, permissions=role.permissions, colour=role.colour, reason="[Anti-Nuke] Restored deleted role")
        except Exception:
            pass
        await self.lockdown(guild, True)
        await self.log_action(guild, "Role Deleted", f"Role `{role.name}` was deleted by {actor.mention}. Role restored and server locked down.")
        if member:
            await self.punish(guild, member, "Deleted a role")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        guild = role.guild
        cfg = self.config(guild.id)
        if not cfg["enabled"] or not cfg["protect_roles"]:
            return
        actor = await self.get_actor(guild, discord.AuditLogAction.role_create)
        if actor is None or actor == self.bot.user:
            return
        member = guild.get_member(actor.id)
        if member and self.is_trusted(member):
            return
        try:
            await role.delete(reason="[Anti-Nuke] Unauthorized role creation")
        except Exception:
            pass
        await self.log_action(guild, "Role Created", f"{actor.mention} created a role without permission. Role deleted.")
        if member:
            await self.punish(guild, member, "Created a role without permission")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        guild = channel.guild
        cfg = self.config(guild.id)
        if not cfg["enabled"] or not cfg["protect_webhooks"]:
            return
        actor = await self.get_actor(guild, discord.AuditLogAction.webhook_create)
        if actor is None or actor == self.bot.user:
            return
        member = guild.get_member(actor.id)
        if member and self.is_trusted(member):
            return
        try:
            for hook in await channel.webhooks():
                await hook.delete(reason="[Anti-Nuke] Unauthorized webhook")
        except Exception:
            pass
        await self.log_action(guild, "Webhook Created", f"{actor.mention} created a webhook without permission. Webhook deleted.")
        if member:
            await self.punish(guild, member, "Created a webhook without permission")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        cfg = self.config(guild.id)
        if not cfg["enabled"] or not cfg["protect_bans"]:
            return
        now = time.time()
        gid = guild.id
        if gid not in self.ban_times:
            self.ban_times[gid] = []
        self.ban_times[gid] = [t for t in self.ban_times[gid] if now - t < cfg["ban_window"]]
        self.ban_times[gid].append(now)
        if len(self.ban_times[gid]) >= cfg["ban_threshold"]:
            self.ban_times[gid] = []
            actor = await self.get_actor(guild, discord.AuditLogAction.ban)
            if actor and actor != self.bot.user:
                await self.lockdown(guild, True)
                await self.log_action(guild, "Mass Ban Detected", f"**{cfg['ban_threshold']}** bans in {cfg['ban_window']}s. Server locked down.")
                member = guild.get_member(actor.id)
                if member and not self.is_trusted(member):
                    await self.punish(guild, member, "Mass banning members")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild
        cfg = self.config(guild.id)
        if not cfg["enabled"] or not cfg["protect_kicks"]:
            return
        actor = await self.get_actor(guild, discord.AuditLogAction.kick)
        if actor is None or actor == self.bot.user:
            return
        now = time.time()
        gid = guild.id
        if gid not in self.kick_times:
            self.kick_times[gid] = []
        self.kick_times[gid] = [t for t in self.kick_times[gid] if now - t < cfg["kick_window"]]
        self.kick_times[gid].append(now)
        if len(self.kick_times[gid]) >= cfg["kick_threshold"]:
            self.kick_times[gid] = []
            await self.lockdown(guild, True)
            await self.log_action(guild, "Mass Kick Detected", f"**{cfg['kick_threshold']}** kicks in {cfg['kick_window']}s. Server locked down.")
            member = guild.get_member(actor.id)
            if member and not self.is_trusted(member):
                await self.punish(guild, member, "Mass kicking members")


async def setup(bot):
    await bot.add_cog(AntiNuke(bot))
