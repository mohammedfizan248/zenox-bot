import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import time
import datetime
import re
import itertools

DATA_FILE = "data/security.json"

INVITE_REGEX = r"(?:discord\.(?:gg|io|me|li)|discordapp\.com/invite)/([a-zA-Z0-9]+)"
LINK_REGEX = r"https?://|www\."
EMOJI_REGEX = r"<a?:\w+:\d+>|[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2705-\u27BF]"


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
    "enabled": True,
    "spam": {"count": 5, "seconds": 5},
    "invite_filter": True,
    "link_filter": False,
    "words": [],
    "mass_mentions": 6,
    "raid": {"joins": 5, "seconds": 30},
    "whitelist": [],
    "verified_role": None,
    "verify_channel": None,
    "emoji_limit": 0,
    "caps_limit": 0,
    "newline_limit": 0,
    "repeat_limit": 0,
    "duplicate_limit": 0,
}


class Security(commands.Cog, name="security"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()
        self.flood = {}
        self.join_times = {}
        self.recent_msgs = {}
        for gid, cfg in self.data.items():
            if cfg.get("verified_role"):
                self.bot.add_view(VerifyView(cfg["verified_role"]))

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

    def is_whitelisted(self, cfg, channel):
        return channel.id in cfg["whitelist"]

    async def log_action(self, guild, title, content, color=discord.Color.red()):
        log = self.bot.get_cog("Logs")
        if log:
            embed = discord.Embed(title=title, description=content, color=color, timestamp=discord.utils.utcnow())
            await log.send_log(guild.id, embed)

    # --- SETTINGS COMMANDS ---
    async def _setsecurity(self, ctx, enabled):
        cfg = self.config(ctx.guild.id)
        cfg["enabled"] = enabled
        save_data(self.data)
        await respond(ctx, content=f"Security is now **{'ON' if enabled else 'OFF'}**.")

    @commands.command(name="setsecurity")
    @commands.has_permissions(administrator=True)
    async def setsecurity_prefix(self, ctx, enabled: str = None):
        if enabled is None:
            cfg = self.config(ctx.guild.id)
            return await ctx.send(f"Security is currently **{'ON' if cfg['enabled'] else 'OFF'}**.")
        await self._setsecurity(ctx, enabled.lower() in ("on", "true", "yes", "1"))

    @app_commands.command(name="setsecurity", description="Enable or disable the security system")
    @app_commands.default_permissions(administrator=True)
    async def setsecurity_slash(self, interaction: discord.Interaction, enabled: bool):
        await self._setsecurity(interaction, enabled)

    async def _setspamlimit(self, ctx, count, seconds):
        cfg = self.config(ctx.guild.id)
        cfg["spam"] = {"count": count, "seconds": seconds}
        save_data(self.data)
        await respond(ctx, content=f"Spam limit set: **{count} messages / {seconds} seconds**.")

    @commands.command(name="setspamlimit")
    @commands.has_permissions(administrator=True)
    async def setspamlimit_prefix(self, ctx, count: int = 5, seconds: int = 5):
        await self._setspamlimit(ctx, count, seconds)

    @app_commands.command(name="setspamlimit", description="Set spam detection threshold")
    @app_commands.default_permissions(administrator=True)
    async def setspamlimit_slash(self, interaction: discord.Interaction, count: app_commands.Range[int, 3, 30] = 5, seconds: app_commands.Range[int, 2, 60] = 5):
        await self._setspamlimit(interaction, count, seconds)

    async def _setfilter(self, ctx, kind, enabled):
        cfg = self.config(ctx.guild.id)
        key = {"invite": "invite_filter", "link": "link_filter"}.get(kind)
        if not key:
            return await respond(ctx, content="Invalid filter type. Use `invite` or `link`.")
        cfg[key] = enabled
        save_data(self.data)
        await respond(ctx, content=f"**{kind.capitalize()} filter** is now **{'ON' if enabled else 'OFF'}**.")

    @commands.command(name="setfilter")
    @commands.has_permissions(administrator=True)
    async def setfilter_prefix(self, ctx, kind: str = None, enabled: str = None):
        if not kind or enabled is None:
            return await ctx.send("Usage: `setfilter <invite|link> <on|off>`")
        await self._setfilter(ctx, kind.lower(), enabled.lower() in ("on", "true", "yes", "1"))

    @app_commands.command(name="setfilter", description="Toggle the invite or link filter")
    @app_commands.default_permissions(administrator=True)
    async def setfilter_slash(self, interaction: discord.Interaction, kind: str, enabled: bool):
        await self._setfilter(interaction, kind.lower(), enabled)

    async def _addword(self, ctx, word):
        cfg = self.config(ctx.guild.id)
        word = word.lower()
        if word in cfg["words"]:
            return await respond(ctx, content=f"`{word}` is already filtered.")
        cfg["words"].append(word)
        save_data(self.data)
        await respond(ctx, content=f"Added `{word}` to the word filter.")

    @commands.command(name="addword")
    @commands.has_permissions(administrator=True)
    async def addword_prefix(self, ctx, *, word):
        await self._addword(ctx, word)

    @app_commands.command(name="addword", description="Add a word to the filter")
    @app_commands.default_permissions(administrator=True)
    async def addword_slash(self, interaction: discord.Interaction, word: str):
        await self._addword(interaction, word)

    async def _removeword(self, ctx, word):
        cfg = self.config(ctx.guild.id)
        word = word.lower()
        if word in cfg["words"]:
            cfg["words"].remove(word)
            save_data(self.data)
            await respond(ctx, content=f"Removed `{word}` from the word filter.")
        else:
            await respond(ctx, content=f"`{word}` is not in the filter.")

    @commands.command(name="removeword")
    @commands.has_permissions(administrator=True)
    async def removeword_prefix(self, ctx, *, word):
        await self._removeword(ctx, word)

    @app_commands.command(name="removeword", description="Remove a word from the filter")
    @app_commands.default_permissions(administrator=True)
    async def removeword_slash(self, interaction: discord.Interaction, word: str):
        await self._removeword(interaction, word)

    async def _setmassmentions(self, ctx, count):
        cfg = self.config(ctx.guild.id)
        cfg["mass_mentions"] = count
        save_data(self.data)
        await respond(ctx, content=f"Mass mention limit set to **{count} mentions**.")

    @commands.command(name="setmassmentions")
    @commands.has_permissions(administrator=True)
    async def setmassmentions_prefix(self, ctx, count: int = 6):
        await self._setmassmentions(ctx, count)

    @app_commands.command(name="setmassmentions", description="Set max mentions before auto-delete")
    @app_commands.default_permissions(administrator=True)
    async def setmassmentions_slash(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 50] = 6):
        await self._setmassmentions(interaction, count)

    async def _setraid(self, ctx, joins, seconds):
        cfg = self.config(ctx.guild.id)
        cfg["raid"] = {"joins": joins, "seconds": seconds}
        save_data(self.data)
        await respond(ctx, content=f"Raid detection set: **{joins} joins / {seconds} seconds**.")

    @commands.command(name="setraid")
    @commands.has_permissions(administrator=True)
    async def setraid_prefix(self, ctx, joins: int = 5, seconds: int = 30):
        await self._setraid(ctx, joins, seconds)

    @app_commands.command(name="setraid", description="Set raid detection threshold")
    @app_commands.default_permissions(administrator=True)
    async def setraid_slash(self, interaction: discord.Interaction, joins: app_commands.Range[int, 3, 20] = 5, seconds: app_commands.Range[int, 10, 120] = 30):
        await self._setraid(interaction, joins, seconds)

    # --- AUTO-MOD LIMITS ---
    def check_automod(self, cfg, content):
        if cfg["emoji_limit"]:
            count = len(re.findall(EMOJI_REGEX, content))
            if count > cfg["emoji_limit"]:
                return f"emoji spam ({count})"
        if cfg["caps_limit"]:
            letters = [c for c in content if c.isalpha()]
            if len(letters) >= 8:
                upper = sum(1 for c in letters if c.isupper())
                percent = int((upper / len(letters)) * 100)
                if percent >= cfg["caps_limit"]:
                    return f"caps lock ({percent}%)"
        if cfg["newline_limit"] and content.count("\n") > cfg["newline_limit"]:
            return "newline spam"
        if cfg["repeat_limit"]:
            longest = max((len(list(g)) for _, g in itertools.groupby(content)), default=0)
            if longest > cfg["repeat_limit"]:
                return "character spam"
        return None

    def check_duplicate(self, cfg, user_id, content):
        if not cfg["duplicate_limit"]:
            return None
        now = time.time()
        if user_id not in self.recent_msgs:
            self.recent_msgs[user_id] = []
        self.recent_msgs[user_id] = [(c, t) for c, t in self.recent_msgs[user_id] if now - t < 10]
        self.recent_msgs[user_id].append((content, now))
        if sum(1 for c, _ in self.recent_msgs[user_id] if c == content) >= cfg["duplicate_limit"]:
            return "duplicate message spam"
        return None

    AUTOMOD_KEYS = {
        "emoji": "emoji_limit",
        "caps": "caps_limit",
        "newlines": "newline_limit",
        "repeats": "repeat_limit",
        "dupe": "duplicate_limit",
    }

    async def _setautomod(self, ctx, trigger, limit):
        key = self.AUTOMOD_KEYS.get(trigger)
        if not key:
            return await respond(ctx, content="Trigger must be one of: emoji, caps, newlines, repeats, dupe.")
        cfg = self.config(ctx.guild.id)
        cfg[key] = limit
        save_data(self.data)
        state = "disabled" if limit == 0 else f"**{limit}**"
        await respond(ctx, content=f"Auto-mod **{trigger}** limit set to {state}.")

    @commands.command(name="setautomod")
    @commands.has_permissions(administrator=True)
    async def setautomod_prefix(self, ctx, trigger: str = None, limit: int = None):
        if not trigger or limit is None:
            return await ctx.send("Usage: `setautomod <emoji|caps|newlines|repeats|dupe> <limit>` (limit 0 disables)")
        await self._setautomod(ctx, trigger.lower(), limit)

    @app_commands.command(name="setautomod", description="Set an auto-mod trigger limit (0 disables)")
    @app_commands.default_permissions(administrator=True)
    async def setautomod_slash(self, interaction: discord.Interaction, trigger: str, limit: app_commands.Range[int, 0, 100] = 0):
        await self._setautomod(interaction, trigger.lower(), limit)

    async def _whitelist(self, ctx, channel):
        if channel is None:
            return await respond(ctx, content="Please specify a channel.")
        cfg = self.config(ctx.guild.id)
        if channel.id in cfg["whitelist"]:
            return await respond(ctx, content=f"{channel.mention} is already whitelisted.")
        cfg["whitelist"].append(channel.id)
        save_data(self.data)
        await respond(ctx, content=f"{channel.mention} whitelisted from all filters.")

    @commands.command(name="whitelist")
    @commands.has_permissions(administrator=True)
    async def whitelist_prefix(self, ctx, channel: discord.TextChannel = None):
        await self._whitelist(ctx, channel)

    @app_commands.command(name="whitelist", description="Exempt a channel from all filters")
    @app_commands.default_permissions(administrator=True)
    async def whitelist_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._whitelist(interaction, channel)

    async def _unwhitelist(self, ctx, channel):
        if channel is None:
            return await respond(ctx, content="Please specify a channel.")
        cfg = self.config(ctx.guild.id)
        if channel.id not in cfg["whitelist"]:
            return await respond(ctx, content=f"{channel.mention} is not whitelisted.")
        cfg["whitelist"].remove(channel.id)
        save_data(self.data)
        await respond(ctx, content=f"{channel.mention} removed from whitelist.")

    @commands.command(name="unwhitelist")
    @commands.has_permissions(administrator=True)
    async def unwhitelist_prefix(self, ctx, channel: discord.TextChannel = None):
        await self._unwhitelist(ctx, channel)

    @app_commands.command(name="unwhitelist", description="Remove a channel from the whitelist")
    @app_commands.default_permissions(administrator=True)
    async def unwhitelist_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._unwhitelist(interaction, channel)

    async def _securitystatus(self, ctx):
        cfg = self.config(ctx.guild.id)
        embed = discord.Embed(title="🛡️ Security Status", color=discord.Color.green())
        embed.add_field(name="System", value="ON" if cfg["enabled"] else "OFF")
        embed.add_field(name="Spam Limit", value=f"{cfg['spam']['count']} msg / {cfg['spam']['seconds']}s")
        embed.add_field(name="Invite Filter", value="ON" if cfg["invite_filter"] else "OFF")
        embed.add_field(name="Link Filter", value="ON" if cfg["link_filter"] else "OFF")
        embed.add_field(name="Mass Mentions", value=f">= {cfg['mass_mentions']}")
        embed.add_field(name="Raid Detection", value=f"{cfg['raid']['joins']} joins / {cfg['raid']['seconds']}s")
        embed.add_field(name="Filtered Words", value=str(len(cfg["words"])))
        embed.add_field(name="Whitelisted Channels", value=str(len(cfg["whitelist"])))
        embed.add_field(name="AutoMod", value=f"Emoji {cfg['emoji_limit'] or 'off'} | Caps {cfg['caps_limit']}% | Newlines {cfg['newline_limit']} | Repeats {cfg['repeat_limit']} | Dupe {cfg['duplicate_limit']}", inline=False)
        await respond(ctx, embed=embed)

    @commands.command(name="securitystatus")
    @commands.has_permissions(administrator=True)
    async def securitystatus_prefix(self, ctx):
        await self._securitystatus(ctx)

    @app_commands.command(name="securitystatus", description="View the current security settings")
    @app_commands.default_permissions(administrator=True)
    async def securitystatus_slash(self, interaction: discord.Interaction):
        await self._securitystatus(interaction)

    # --- VERIFICATION ---
    async def _setverify(self, ctx, role, channel):
        cfg = self.config(ctx.guild.id)
        cfg["verified_role"] = role.id if role else None
        cfg["verify_channel"] = channel.id if channel else None
        save_data(self.data)
        await respond(ctx, content=f"Verification configured. Role: {role.mention if role else 'None'} | Channel: {channel.mention if channel else 'None'}")

    @commands.command(name="setverify")
    @commands.has_permissions(administrator=True)
    async def setverify_prefix(self, ctx, role: discord.Role = None, channel: discord.TextChannel = None):
        await self._setverify(ctx, role, channel)

    @app_commands.command(name="setverify", description="Set verification role and channel")
    @app_commands.default_permissions(administrator=True)
    async def setverify_slash(self, interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel):
        await self._setverify(interaction, role, channel)

    async def _verifypanel(self, ctx):
        cfg = self.config(ctx.guild.id)
        if not cfg["verify_channel"]:
            return await respond(ctx, content="Set a verify channel first: `setverify <role> <channel>`")
        if not cfg["verified_role"]:
            return await respond(ctx, content="Set a verified role first: `setverify <role> <channel>`")
        channel = ctx.guild.get_channel(cfg["verify_channel"])
        if not channel:
            return await respond(ctx, content="Verify channel not found.")
        embed = discord.Embed(title="✅ Verification", description="Click the button below to verify yourself and gain access to the server!", color=discord.Color.green())
        view = VerifyView(cfg["verified_role"])
        await channel.send(embed=embed, view=view)
        await respond(ctx, content=f"Verification panel sent to {channel.mention}.")

    @commands.command(name="verifypanel")
    @commands.has_permissions(administrator=True)
    async def verifypanel_prefix(self, ctx):
        await self._verifypanel(ctx)

    @app_commands.command(name="verifypanel", description="Send the verification panel")
    @app_commands.default_permissions(administrator=True)
    async def verifypanel_slash(self, interaction: discord.Interaction):
        await self._verifypanel(interaction)

    # --- LISTENERS ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        cfg = self.config(message.guild.id)
        if not cfg["enabled"]:
            return
        if self.is_whitelisted(cfg, message.channel):
            return
        author = message.author
        if author.guild_permissions.administrator or author.guild_permissions.manage_messages:
            return
        content = message.content.lower()
        reason = None
        if cfg["words"] and any(w in content for w in cfg["words"]):
            reason = "filtered word"
        if cfg["invite_filter"] and __import__("re").search(INVITE_REGEX, content):
            reason = "invite link"
        if cfg["link_filter"] and __import__("re").search(LINK_REGEX, content):
            reason = "external link"
        mentions = len(set(m.id for m in message.mentions)) + len(set(r.id for r in message.role_mentions))
        if cfg["mass_mentions"] and mentions >= cfg["mass_mentions"]:
            reason = f"mass mention ({mentions})"
        if reason is None:
            reason = self.check_automod(cfg, content)
        if reason is None:
            reason = self.check_duplicate(cfg, author.id, message.content)
        if reason:
            try:
                await message.delete()
                await message.channel.send(f"{author.mention} your message was deleted: **{reason}**.", delete_after=5)
                await self.log_action(message.guild, "Message Deleted", f"{author.mention} sent a message with {reason}\nContent: {message.content[:200]}")
                prot = self.bot.get_cog("Protection")
                if prot:
                    await prot.record_offense(message.guild, author, reason)
            except:
                pass
            return
        now = time.time()
        uid = author.id
        if uid not in self.flood:
            self.flood[uid] = []
        self.flood[uid] = [t for t in self.flood[uid] if now - t < cfg["spam"]["seconds"]]
        self.flood[uid].append(now)
        if len(self.flood[uid]) > cfg["spam"]["count"]:
            try:
                await message.delete()
                self.flood[uid] = []
                await message.channel.send(f"🚫 {author.mention} stop spamming!", delete_after=5)
                await self.log_action(message.guild, "Spam Detected", f"{author.mention} was spamming.")
                prot = self.bot.get_cog("Protection")
                if prot:
                    await prot.record_offense(message.guild, author, "spamming")
            except:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member):
        cfg = self.config(member.guild.id)
        now = time.time()
        gid = member.guild.id
        if gid not in self.join_times:
            self.join_times[gid] = []
        self.join_times[gid] = [t for t in self.join_times[gid] if now - t < cfg["raid"]["seconds"]]
        self.join_times[gid].append(now)
        if len(self.join_times[gid]) > cfg["raid"]["joins"]:
            await self.log_action(member.guild, "⚠️ Possible Raid Detected", f"**{len(self.join_times[gid])}** members joined in {cfg['raid']['seconds']} seconds.", color=discord.Color.orange())
            prot = self.bot.get_cog("Protection")
            if prot:
                await prot.trigger_panic(member.guild, reason="Raid detected (mass joins)")


class VerifyView(discord.ui.View):
    def __init__(self, role_id):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_me")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)
        if role is None:
            return await interaction.response.send_message("Verified role no longer exists.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message("You are already verified!", ephemeral=True)
        await interaction.user.add_roles(role, reason="Verified")
        await interaction.response.send_message("You are now verified! Welcome in 🎉", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Security(bot))
