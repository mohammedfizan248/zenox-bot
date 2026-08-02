import discord
from discord import app_commands
from discord.ext import commands
import config
import os
import http.server
import threading

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=config.PREFIX, intents=intents, help_command=None)

HELP_CATEGORIES = ["moderation", "welcome", "utility", "fun", "music", "admin", "tickets", "apply", "logs", "selfroles", "security", "protection", "samp", "db"]

HELP_TEXTS = {
    "moderation": {
        "title": "Moderation Commands",
        "desc": "Keep your server safe and clean.",
        "cmds": [
            "kick <member> [reason] - Kick a member",
            "ban <member> [reason] [days=0] - Ban a member",
            "unban <user#1234> - Unban a user",
            "mute <member> [duration_m] [reason] - Mute a member",
            "unmute <member> - Unmute a member",
            "warn <member> [reason] - Warn a member",
            "warnings <member> - List warnings for a member",
            "clearwarns <member> - Clear all warnings",
            "purge <count> - Bulk delete messages",
            "clear <count|all> - Clear messages from a channel",
            "addroleall <role> - Add a role to all members",
            "removeroleall <role> - Remove a role from all members",
        ],
    },
    "welcome": {
        "title": "Welcome Commands",
        "desc": "Manage welcome messages and auto-roles.",
        "cmds": [
            "setwelcome <channel> - Set the welcome channel",
            "setwelcomemsg <message> - Set the welcome message",
            "setwelcomeimage <url> - Set a banner image for welcome",
            "setautorole <role> - Set the auto-role for new members",
            "testwelcome - Test the welcome message",
        ],
    },
    "utility": {
        "title": "Utility Commands",
        "desc": "Useful everyday commands.",
        "cmds": [
            "userinfo [member] - Show user info",
            "serverinfo - Show server info",
            "roleinfo <role> - Show role info",
            "avatar [member] - Show a user's avatar",
            "poll <question> | <option1> | <option2> ... - Create a poll",
            "remind <duration_m> <message> - Set a reminder",
            "ping - Check bot latency",
        ],
    },
    "fun": {
        "title": "Fun Commands",
        "desc": "Games, economy, and engagement.",
        "cmds": [
            "balance [member] - Show economy balance",
            "daily - Claim your daily reward",
            "give <member> <amount> - Give coins to someone",
            "slots <bet> - Play slots",
            "8ball <question> - Ask the magic 8ball",
            "meme - Get a random meme",
        ],
    },
    "music": {
        "title": "Music Commands",
        "desc": "Listen to music together.",
        "cmds": [
            "play <song/url> - Play a song",
            "skip - Skip the current song",
            "stop - Stop music and clear queue",
            "queue - Show the song queue",
            "nowplaying - Show the current song",
            "volume <0-100> - Set volume",
            "pause - Pause playback",
            "resume - Resume playback",
        ],
    },
    "admin": {
        "title": "Admin Commands",
        "desc": "Bot administration.",
        "cmds": [
            "reload <cog> - Reload a cog",
            "guilds - List connected servers",
            "say <message> - Make the bot say something",
            "dm <member> <message> - DM a member through the bot",
        ],
    },
    "tickets": {
        "title": "Ticket Commands",
        "desc": "Support ticket system.",
        "cmds": [
            "settickets <category> [mod_role] - Set up the ticket system",
            "renovate - Re-post the ticket panel",
            "adduser <member> - Add a user to the ticket",
            "removeuser <member> - Remove a user from the ticket",
            "transcript - Get the ticket transcript",
        ],
    },
    "apply": {
        "title": "Whitelist Apply",
        "desc": "Whitelist application system.",
        "cmds": [
            "setapplychannel <channel> - Set the applications channel (sends the apply panel)",
            "setapplyquestions <q1|q2|...> - Set questions (max 5)",
            "apply - Submit a whitelist application",
            "accept <member> [app_id] - Accept an application",
            "deny <member> [app_id] [reason] - Deny an application",
            "applications [status] - List applications",
        ],
    },
    "logs": {
        "title": "Logs",
        "desc": "Server logging system.",
        "cmds": [
            "setlogchannel <channel> - Set the logging channel",
        ],
    },
    "selfroles": {
        "title": "Self Roles",
        "desc": "Let members assign roles to themselves with buttons.",
        "cmds": [
            "setselfroles <channel> [\"message\"] <@role1> <@role2> ... - Create a self-role panel",
            "removeselfroles <channel> - Remove panels from a channel",
        ],
    },
    "security": {
        "title": "Security",
        "desc": "Anti-spam, filters, raid protection, and verification.",
        "cmds": [
            "setsecurity <on|off> - Enable/disable the security system",
            "setspamlimit <count> <seconds> - Spam detection threshold",
            "setfilter <invite|link> <on|off> - Toggle filters",
            "addword <word> / removeword <word> - Manage word filter",
            "setmassmentions <count> - Max mentions before auto-delete",
            "setraid <joins> <seconds> - Raid detection",
            "whitelist <channel> / unwhitelist <channel> - Exempt channels",
            "setverify <role> <channel> - Set verification role/channel",
            "verifypanel - Send the verification button panel",
            "securitystatus - View current security settings",
        ],
    },
    "samp": {
        "title": "SA-MP Server",
        "desc": "Monitor your SA-MP (GTA San Andreas) server.",
        "cmds": [
            "sampsetip <host:port> - Set your SA-MP server address",
            "sampstatus - Show live server info and player count",
            "sampplayers - List online players with score/ping",
            "samprules - Show server rules",
            "sampsetstatus <channel> - Auto-update a channel with player count",
            "sampstopstatus - Stop the auto status updates",
        ],
    },
    "protection": {
        "title": "Protection (Wick-style)",
        "desc": "Anti-nuke, raid, ghost ping, and auto-punishment protection.",
        "cmds": [
            "protectionpanel - Send the protection dashboard with toggle buttons",
            "protectionstatus - View the current protection settings",
            "lockdown [reason] - Lock the whole server instantly",
            "unlock [reason] - Unlock the server after a lockdown",
            "setaccountage <days> [verify|kick|mute] - New-account protection (0 disables)",
        ],
    },
    "db": {
        "title": "In-Game Database",
        "desc": "View stats from the SA-MP roleplay database.",
        "cmds": [
            "stats <name> - View a player's in-game stats",
            "top [level|cash] - Top players by level or cash",
            "admins - List admins and helpers",
            "faction [name] - List factions or view a faction's members",
            "gang [name] - List gangs or view a gang's members",
        ],
    },
}


def build_help_embed(category: str = None):
    if category is None:
        embed = discord.Embed(
            title="Community Bot Help",
            description=f"Commands work with `{config.PREFIX}` prefix OR `/` slash.\nUse `/help <category>` or `{config.PREFIX}help <category>` for details.",
            color=discord.Color.blue(),
        )
        for cat in HELP_CATEGORIES:
            embed.add_field(name=cat.capitalize(), value=f"`/help {cat}`", inline=True)
        return embed
    data = HELP_TEXTS.get(category.lower())
    if not data:
        return None
    embed = discord.Embed(title=data["title"], description=data["desc"], color=discord.Color.green())
    for cmd in data["cmds"]:
        parts = cmd.split(" - ", 1)
        name = parts[0].strip()
        if not name.startswith("/"):
            name = "/" + name
        embed.add_field(name=name, value=parts[1] if len(parts) > 1 else cmd, inline=False)
    return embed


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    if not bot.owner_id:
        app_info = await bot.application_info()
        bot.owner_id = app_info.owner.id
    print(f"Prefix commands: {[c.name for c in bot.commands]}")
    for guild in bot.guilds:
        try:
            bot.tree.clear_commands(guild=guild)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Guild {guild.id}: {len(synced)} commands synced")
        except Exception as e:
            print(f"Guild sync error for {guild.id}: {e}")
    print("------")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"/help | {len(bot.guilds)} servers",
        )
    )


@bot.event
async def on_command_error(ctx, error):
    print(f"Command error: {ctx.command} - {error}")
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(f"Error: {error}")


@bot.event
async def on_app_command_error(interaction, error):
    print(f"Slash error: {error}")
    if not interaction.response.is_done():
        await interaction.response.send_message(f"Error: {error}", ephemeral=True)


async def load_cogs():
    for cog in ["cogs.moderation", "cogs.welcome", "cogs.utility", "cogs.fun", "cogs.music", "cogs.admin", "cogs.tickets", "cogs.apply", "cogs.logs", "cogs.selfroles", "cogs.security", "cogs.protection", "cogs.samp", "cogs.database"]:
        await bot.load_extension(cog)
        print(f"Loaded {cog}")


@bot.command(name="help")
async def help_prefix(ctx, *, category: str = None):
    embed = build_help_embed(category)
    if embed is None:
        await ctx.send(f"Unknown category. Use `{config.PREFIX}help` to see categories.")
        return
    view = HelpView() if category is None else None
    await ctx.send(embed=embed, view=view)


class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=cat.capitalize(), value=cat, description=HELP_TEXTS[cat]["desc"])
            for cat in HELP_CATEGORIES
        ]
        super().__init__(placeholder="Choose a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        embed = build_help_embed(self.values[0])
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpSelect())


@bot.tree.command(name="help", description="Show bot commands")
async def help_slash(interaction: discord.Interaction, category: str = None):
    if category:
        embed = build_help_embed(category.lower())
        if embed is None:
            await interaction.response.send_message(
                "Unknown category. Use `/help` to see the list of categories.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=embed)
        return
    embed = build_help_embed()
    await interaction.response.send_message(embed=embed, view=HelpView())


@bot.command(name="sync")
@commands.is_owner()
async def sync_prefix(ctx):
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"Synced {len(synced)} slash command(s) to this server.")


@bot.tree.command(name="sync", description="Sync slash commands to this server (owner only)")
async def sync_slash(interaction: discord.Interaction):
    if not await bot.is_owner(interaction.user):
        await interaction.response.send_message("Only the bot owner can use this.", ephemeral=True)
        return
    bot.tree.copy_global_to(guild=interaction.guild)
    synced = await bot.tree.sync(guild=interaction.guild)
    await interaction.response.send_message(f"Synced {len(synced)} slash command(s).", ephemeral=True)


def start_health_server():
    port = int(os.getenv("PORT", "10000"))

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    try:
        server = http.server.HTTPServer(("0.0.0.0", port), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"Health server listening on port {port}")
    except Exception as e:
        print(f"Health server could not start: {e}")


async def main():
    start_health_server()
    async with bot:
        await load_cogs()
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
