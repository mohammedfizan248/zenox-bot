import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import time
import datetime
import re


DATA_FILE = "data/protection.json"

DEFAULT_CONFIG = {
    "anti_nuke": True,
    "nuke": {"channel_del": 4, "role_del": 4, "ban": 3, "kick": 5, "bot_add": 1, "channel_create": 6, "role_create": 6, "window": 10},
    "account_age_days": 7,
    "new_account_action": "verify",
    "ghost_ping": True,
    "auto_punish": True,
    "lockdown": False,
    "lockdown_overwrites": {},
    "trusted_bots": [],
    "offenses": {},
}


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


class Protection(commands.Cog, name="protection"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()
        self.actions = {}
        self.deleted_channels = {}
        self.deleted_roles = {}
        self.recent = {}
        self.bot.add_view(ProtectionPanelView())

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

    async def log_action(self, guild, title, description, color=discord.Color.red()):
        log = self.bot.get_cog("Logs")
        if log:
            embed = discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())
            await log.send_log(guild.id, embed)

    def enabled(self, guild_id):
        return self.config(guild_id)["anti_nuke"]

    # ---- internal helpers ----
    def record_action(self, guild, action):
        gid = guild.id
        now = time.time()
        window = self.config(gid)["nuke"]["window"]
        if gid not in self.actions:
            self.actions[gid] = []
        self.actions[gid] = [t for t in self.actions[gid] if now - t < window]
        self.actions[gid].append((action, now))
        self.prune_snapshots(guild)

    def count_actions(self, guild, action):
        gid = guild.id
        if gid not in self.actions:
            return 0
        return sum(1 for a, _ in self.actions[gid] if a == action)

    def prune_snapshots(self, guild):
        gid = guild.id
        now = time.time()
        for store in (self.deleted_channels, self.deleted_roles):
            if gid in store:
                store[gid] = [s for s in store[gid] if now - s["ts"] < 60]

    async def get_actor(self, guild, action, limit=10):
        try:
            async for entry in guild.audit_logs(limit=limit, action=action):
                return entry.user
        except Exception:
            return None
        return None

    def tier_for(self, count):
        if count >= 4:
            return "ban"
        if count == 3:
            return "kick"
        if count == 2:
            return "mute"
        return "warn"

    async def record_offense(self, guild, member, reason):
        cfg = self.config(guild.id)
        if not cfg["auto_punish"]:
            return
        uid = str(member.id)
        offenses = cfg["offenses"]
        now = time.time()
        if uid in offenses and now - offenses[uid]["ts"] > 86400:
            offenses[uid] = {"count": 0, "ts": now}
        entry = offenses.get(uid, {"count": 0, "ts": now})
        entry["count"] += 1
        entry["ts"] = now
        entry["reason"] = reason
        offenses[uid] = entry
        save_data(self.data)
        tier = self.tier_for(entry["count"])
        await self.log_action(guild, "Auto-Punish", f"{member.mention} ({member.id}) - offense #{entry['count']} for {reason} -> **{tier}**", color=discord.Color.orange())
        if tier == "warn":
            try:
                await member.send(f"⚠️ **Warning** ({guild.name}): {reason}\nOffense {entry['count']}/4. Next offense gets a mute.")
            except Exception:
                pass
        elif tier == "mute":
            try:
                await member.timeout(discord.utils.utcnow() + datetime.timedelta(minutes=10), reason=f"Auto-punish: {reason}")
            except Exception:
                pass
        elif tier == "kick":
            try:
                await member.kick(reason=f"Auto-punish: {reason}")
            except Exception:
                pass
        elif tier == "ban":
            try:
                await member.ban(reason=f"Auto-punish: {reason}")
            except Exception:
                pass

    async def lockdown(self, guild, reason=None):
        cfg = self.config(guild.id)
        if cfg["lockdown"]:
            return False
        stored = {}
        perms = discord.PermissionOverwrite(send_messages=False, add_reactions=False)
        for channel in guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                overwrites = channel.overwrites
                saved = {}
                for target, ov in overwrites.items():
                    saved[str(target.id)] = {"allow": ov.pair()[0].value, "deny": ov.pair()[1].value}
                if guild.default_role in overwrites:
                    saved[str(guild.default_role.id)] = {"allow": overwrites[guild.default_role].pair()[0].value, "deny": overwrites[guild.default_role].pair()[1].value}
                stored[str(channel.id)] = saved
                try:
                    await channel.set_permissions(guild.default_role, overwrite=perms, reason=f"Lockdown: {reason or 'security'}")
                except Exception:
                    pass
        cfg["lockdown"] = True
        cfg["lockdown_overwrites"] = stored
        save_data(self.data)
        await self.log_action(guild, "🔒 Server Locked", f"All text channels locked.\nReason: {reason or 'Security event'}", color=discord.Color.red())
        return True

    async def unlock(self, guild, reason=None):
        cfg = self.config(guild.id)
        if not cfg["lockdown"]:
            return False
        stored = cfg.get("lockdown_overwrites", {})
        for channel in guild.channels:
            if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                saved = stored.get(str(channel.id))
                try:
                    if saved is None:
                        await channel.set_permissions(guild.default_role, overwrite=None, reason=f"Unlock: {reason or 'All clear'}")
                    else:
                        await channel.set_permissions(guild.default_role, overwrite=None)
                        for tid, ov in saved.items():
                            target = guild.get_role(int(tid)) or guild.get_member(int(tid))
                            if target is None:
                                continue
                            await channel.set_permissions(target, overwrite=discord.PermissionOverwrite(allow=ov["allow"], deny=ov["deny"]))
                except Exception:
                    pass
        cfg["lockdown"] = False
        cfg["lockdown_overwrites"] = {}
        save_data(self.data)
        await self.log_action(guild, "🔓 Server Unlocked", f"Channels restored.\nReason: {reason or 'All clear'}", color=discord.Color.green())
        return True

    async def trigger_panic(self, guild, reason=None):
        await self.lockdown(guild, reason=reason)
        await self.log_action(guild, "🚨 Protection Triggered", reason or "Security event detected", color=discord.Color.red())

    # ---- anti-nuke response ----
    async def handle_nuke(self, guild, action_name, actor=None):
        cfg = self.config(guild.id)
        if not cfg["anti_nuke"]:
            return
        if actor is None:
            actor = await self.get_actor(guild, action_name)
        if actor is None or actor.id == self.bot.user.id:
            return
        if actor.id == guild.owner_id:
            return
        await self.log_action(guild, "💥 Nuke Detected", f"Attacker: {actor.mention} ({actor.id})\nAction: {action_name}\nLocking down server...", color=discord.Color.red())
        try:
            await actor.ban(reason=f"Anti-nuke: mass destructive actions ({action_name})")
        except Exception:
            pass
        await self.lockdown(guild, reason="Anti-nuke triggered")
        await self.restore_deleted(guild)

    async def restore_deleted(self, guild):
        gid = guild.id
        if gid in self.deleted_channels:
            for snap in self.deleted_channels[gid]:
                try:
                    category = guild.get_channel(snap.get("category_id"))
                    await guild.create_text_channel(
                        name=snap["name"],
                        category=category,
                        topic=snap.get("topic", ""),
                        position=snap.get("position", 0),
                    )
                except Exception:
                    pass
        if gid in self.deleted_roles:
            for snap in self.deleted_roles[gid]:
                try:
                    await guild.create_role(
                        name=snap["name"],
                        color=snap.get("color", 0),
                        permissions=discord.Permissions(snap.get("permissions", 0)),
                        hoist=snap.get("hoist", False),
                        mentionable=snap.get("mentionable", False),
                    )
                except Exception:
                    pass

    # ---- listeners: anti-nuke ----
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not channel.guild:
            return
        gid = channel.guild.id
        if not self.enabled(gid):
            return
        self.record_action(channel.guild, "channel_del")
        if gid not in self.deleted_channels:
            self.deleted_channels[gid] = []
        self.deleted_channels[gid].append({
            "ts": time.time(),
            "name": channel.name,
            "category_id": channel.category_id,
            "topic": getattr(channel, "topic", ""),
            "position": channel.position,
        })
        if self.count_actions(channel.guild, "channel_del") >= self.config(gid)["nuke"]["channel_del"]:
            await self.handle_nuke(channel.guild, discord.AuditLogAction.channel_delete)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        if not role.guild:
            return
        gid = role.guild.id
        if not self.enabled(gid):
            return
        self.record_action(role.guild, "role_del")
        if gid not in self.deleted_roles:
            self.deleted_roles[gid] = []
        self.deleted_roles[gid].append({
            "ts": time.time(),
            "name": role.name,
            "color": role.color.value,
            "permissions": role.permissions.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
        })
        if self.count_actions(role.guild, "role_del") >= self.config(gid)["nuke"]["role_del"]:
            await self.handle_nuke(role.guild, discord.AuditLogAction.role_delete)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not channel.guild:
            return
        gid = channel.guild.id
        if not self.enabled(gid):
            return
        self.record_action(channel.guild, "channel_create")
        if self.count_actions(channel.guild, "channel_create") >= self.config(gid)["nuke"]["channel_create"]:
            await self.handle_nuke(channel.guild, discord.AuditLogAction.channel_create)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        if not role.guild:
            return
        gid = role.guild.id
        if not self.enabled(gid):
            return
        self.record_action(role.guild, "role_create")
        if self.count_actions(role.guild, "role_create") >= self.config(gid)["nuke"]["role_create"]:
            await self.handle_nuke(role.guild, discord.AuditLogAction.role_create)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if not self.enabled(guild.id):
            return
        self.record_action(guild, "ban")
        if self.count_actions(guild, "ban") >= self.config(guild.id)["nuke"]["ban"]:
            await self.handle_nuke(guild, discord.AuditLogAction.ban)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not self.enabled(member.guild.id):
            return
        if member.bot:
            return
        try:
            async for entry in member.guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
                if entry.target and entry.target.id == member.id:
                    self.record_action(member.guild, "kick")
                    if self.count_actions(member.guild, "kick") >= self.config(member.guild.id)["nuke"]["kick"]:
                        await self.handle_nuke(member.guild, discord.AuditLogAction.kick)
                    break
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member):
        gid = member.guild.id
        cfg = self.config(gid)
        if member.bot:
            if cfg["anti_nuke"] and member.id not in cfg["trusted_bots"]:
                self.record_action(member.guild, "bot_add")
                if self.count_actions(member.guild, "bot_add") >= cfg["nuke"]["bot_add"]:
                    await self.handle_nuke(member.guild, discord.AuditLogAction.bot_add)
                    return
                try:
                    await member.kick(reason="Unapproved bot added")
                    await self.log_action(member.guild, "🤖 Bot Added", f"{member.mention} was added but is not approved and was kicked.")
                except Exception:
                    pass
            return
        if cfg.get("account_age_days"):
            age = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
            if age < cfg["account_age_days"]:
                action = cfg.get("new_account_action", "verify")
                await self.log_action(member.guild, "👤 New Account", f"{member.mention} account is only **{age} days** old.\nAction: {action}", color=discord.Color.orange())
                if action == "kick":
                    try:
                        await member.kick(reason=f"Account younger than {cfg['account_age_days']} days")
                    except Exception:
                        pass
                elif action == "mute":
                    try:
                        await member.timeout(discord.utils.utcnow() + datetime.timedelta(days=1), reason="New account review")
                    except Exception:
                        pass

    # ---- ghost ping ----
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        cfg = self.config(message.guild.id)
        if not cfg["ghost_ping"]:
            return
        mentions = [m.id for m in message.mentions if m.id != message.author.id]
        if mentions:
            gid = message.guild.id
            if gid not in self.recent:
                self.recent[gid] = {}
            self.recent[gid][message.id] = {
                "author": message.author.id,
                "channel": message.channel.id,
                "mentions": set(mentions),
                "ts": time.time(),
            }
            self.recent[gid] = {k: v for k, v in self.recent[gid].items() if time.time() - v["ts"] < 60}

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return
        cfg = self.config(message.guild.id)
        if not cfg["ghost_ping"]:
            return
        rec = self.recent.get(message.guild.id, {}).pop(message.id, None)
        if not rec:
            return
        if time.time() - rec["ts"] > 60:
            return
        if rec["mentions"]:
            targets = " ".join(f"<@{i}>" for i in list(rec["mentions"])[:5])
            await self.log_action(message.guild, "👻 Ghost Ping", f"{message.author.mention} pinged {targets} then deleted the message.", color=discord.Color.orange())
            await self.record_offense(message.guild, message.author, "ghost ping")

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild:
            return
        cfg = self.config(before.guild.id)
        if not cfg["ghost_ping"]:
            return
        b = set(m.id for m in before.mentions if m.id != before.author.id) | set(r.id for r in before.role_mentions) | set(c.id for c in before.channel_mentions)
        a = set(m.id for m in after.mentions if m.id != before.author.id) | set(r.id for r in after.role_mentions) | set(c.id for c in after.channel_mentions)
        if b and not (b <= a):
            removed = b - a
            targets = " ".join(f"<@{i}>" if i > 2 ** 40 else f"<#{i}>" for i in list(removed)[:5])
            await self.log_action(before.guild, "👻 Ghost Ping", f"{before.author.mention} removed mentions to {targets} by editing a message.", color=discord.Color.orange())
            await self.record_offense(before.guild, before.author, "ghost ping (edit)")

    # ---- lockdown commands ----
    async def _lockdown(self, ctx, reason):
        await self.lockdown(ctx.guild, reason=reason)
        await respond(ctx, content="🔒 **Server locked.** All text channels are now read-only.")

    async def _unlock(self, ctx, reason):
        await self.unlock(ctx.guild, reason=reason)
        await respond(ctx, content="🔓 **Server unlocked.** Channels restored.")

    @commands.command(name="lockdown")
    @commands.has_permissions(administrator=True)
    async def lockdown_prefix(self, ctx, *, reason: str = None):
        await self._lockdown(ctx, reason)

    @app_commands.command(name="lockdown", description="Lock the entire server (read-only mode)")
    @app_commands.default_permissions(administrator=True)
    async def lockdown_slash(self, interaction: discord.Interaction, reason: str = None):
        await self._lockdown(interaction, reason)

    @commands.command(name="unlock")
    @commands.has_permissions(administrator=True)
    async def unlock_prefix(self, ctx, *, reason: str = None):
        await self._unlock(ctx, reason)

    @app_commands.command(name="unlock", description="Unlock the server after a lockdown")
    @app_commands.default_permissions(administrator=True)
    async def unlock_slash(self, interaction: discord.Interaction, reason: str = None):
        await self._unlock(interaction, reason)

    # ---- settings ----
    async def _setaccountage(self, ctx, days, action):
        cfg = self.config(ctx.guild.id)
        cfg["account_age_days"] = days
        if action:
            cfg["new_account_action"] = action
        save_data(self.data)
        await respond(ctx, content=f"New-account protection set to **{days} days** (action: {cfg['new_account_action']}).")

    @commands.command(name="setaccountage")
    @commands.has_permissions(administrator=True)
    async def setaccountage_prefix(self, ctx, days: int = 7, action: str = None):
        await self._setaccountage(ctx, days, action.lower() if action in ("verify", "kick", "mute") else None)

    @app_commands.command(name="setaccountage", description="Set new-account protection (0 to disable)")
    @app_commands.default_permissions(administrator=True)
    async def setaccountage_slash(self, interaction: discord.Interaction, days: app_commands.Range[int, 0, 90] = 7, action: str = None):
        await self._setaccountage(interaction, days, action.lower() if action else None)

    async def _protectionstatus(self, ctx):
        cfg = self.config(ctx.guild.id)
        embed = discord.Embed(title="🛡️ Protection Status", color=discord.Color.blue())
        embed.add_field(name="Anti-Nuke", value="✅ ON" if cfg["anti_nuke"] else "❌ OFF")
        embed.add_field(name="Ghost Ping", value="✅ ON" if cfg["ghost_ping"] else "❌ OFF")
        embed.add_field(name="Auto-Punish", value="✅ ON" if cfg["auto_punish"] else "❌ OFF")
        embed.add_field(name="New Account", value=f"{'✅ ON' if cfg['account_age_days'] else '❌ OFF'} ({cfg['account_age_days']}d - {cfg['new_account_action']})")
        embed.add_field(name="Lockdown", value="🔒 Active" if cfg["lockdown"] else "🔓 Inactive")
        embed.add_field(name="Trusted Bots", value=str(len(cfg["trusted_bots"])))
        await respond(ctx, embed=embed)

    @commands.command(name="protectionstatus")
    @commands.has_permissions(administrator=True)
    async def protectionstatus_prefix(self, ctx):
        await self._protectionstatus(ctx)

    @app_commands.command(name="protectionstatus", description="View the protection system status")
    @app_commands.default_permissions(administrator=True)
    async def protectionstatus_slash(self, interaction: discord.Interaction):
        await self._protectionstatus(interaction)

    async def _protectionpanel(self, ctx):
        channel = ctx.channel if hasattr(ctx, "channel") else ctx
        await channel.send(embed=build_panel_embed(self.config(channel.guild.id)), view=ProtectionPanelView())
        await respond(ctx, content="Protection panel sent.")

    @commands.command(name="protectionpanel")
    @commands.has_permissions(administrator=True)
    async def protectionpanel_prefix(self, ctx):
        await self._protectionpanel(ctx)

    @app_commands.command(name="protectionpanel", description="Send the protection dashboard panel")
    @app_commands.default_permissions(administrator=True)
    async def protectionpanel_slash(self, interaction: discord.Interaction):
        await self._protectionpanel(interaction)

    async def toggle(self, guild, key, enabled=None):
        cfg = self.config(guild.id)
        if enabled is None:
            cfg[key] = not cfg[key]
        else:
            cfg[key] = enabled
        save_data(self.data)
        return cfg[key]


def build_panel_embed(cfg):
    embed = discord.Embed(title="🛡️ Protection Dashboard", description="Click a button to toggle each protection.", color=discord.Color.blue())
    embed.add_field(name="Anti-Nuke", value="🟢 Enabled" if cfg["anti_nuke"] else "🔴 Disabled", inline=True)
    embed.add_field(name="New-Account", value="🟢 Enabled" if cfg["account_age_days"] else "🔴 Disabled", inline=True)
    embed.add_field(name="Ghost Ping", value="🟢 Enabled" if cfg["ghost_ping"] else "🔴 Disabled", inline=True)
    embed.add_field(name="Auto-Punish", value="🟢 Enabled" if cfg["auto_punish"] else "🔴 Disabled", inline=True)
    embed.add_field(name="Lockdown", value="🔒 Active" if cfg["lockdown"] else "🔓 Inactive", inline=True)
    return embed


class ProtectionPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def get_cog(self, interaction):
        cog = interaction.client.get_cog("Protection")
        return cog

    def is_admin(self, interaction):
        return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild

    def sync_embed(self, cog, interaction):
        return build_panel_embed(cog.config(interaction.guild.id))

    @discord.ui.button(label="Anti-Nuke", style=discord.ButtonStyle.danger, emoji="💥", custom_id="prot_toggle_antinuke")
    async def btn_antinuke(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("Only admins can change protections.", ephemeral=True)
        cog = await self.get_cog(interaction)
        state = await cog.toggle(interaction.guild, "anti_nuke")
        await interaction.response.edit_message(embed=self.sync_embed(cog, interaction), view=self)

    @discord.ui.button(label="New-Account", style=discord.ButtonStyle.danger, emoji="👤", custom_id="prot_toggle_account")
    async def btn_account(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("Only admins can change protections.", ephemeral=True)
        cog = await self.get_cog(interaction)
        cfg = cog.config(interaction.guild.id)
        cfg["account_age_days"] = 7 if not cfg["account_age_days"] else 0
        save_data(cog.data)
        await interaction.response.edit_message(embed=self.sync_embed(cog, interaction), view=self)

    @discord.ui.button(label="Ghost Ping", style=discord.ButtonStyle.danger, emoji="👻", custom_id="prot_toggle_ghost")
    async def btn_ghost(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("Only admins can change protections.", ephemeral=True)
        cog = await self.get_cog(interaction)
        state = await cog.toggle(interaction.guild, "ghost_ping")
        await interaction.response.edit_message(embed=self.sync_embed(cog, interaction), view=self)

    @discord.ui.button(label="Auto-Punish", style=discord.ButtonStyle.danger, emoji="⚖️", custom_id="prot_toggle_punish")
    async def btn_punish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("Only admins can change protections.", ephemeral=True)
        cog = await self.get_cog(interaction)
        state = await cog.toggle(interaction.guild, "auto_punish")
        await interaction.response.edit_message(embed=self.sync_embed(cog, interaction), view=self)

    @discord.ui.button(label="Lockdown", style=discord.ButtonStyle.primary, emoji="🔒", custom_id="prot_toggle_lockdown")
    async def btn_lockdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("Only admins can change protections.", ephemeral=True)
        cog = await self.get_cog(interaction)
        cfg = cog.config(interaction.guild.id)
        if cfg["lockdown"]:
            await cog.unlock(interaction.guild, reason="Unlocked from panel")
        else:
            await cog.lockdown(interaction.guild, reason="Locked from panel")
        await interaction.response.edit_message(embed=self.sync_embed(cog, interaction), view=self)


async def setup(bot):
    await bot.add_cog(Protection(bot))
