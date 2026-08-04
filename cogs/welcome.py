import discord
from discord import app_commands
from discord.ext import commands
import json
import os

DATA_FILE = "data/welcome.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        return {}


def extract_sticker_id(text):
    if not text:
        return None
    text = text.strip()
    if text.isdigit():
        return int(text)
    import re
    m = re.search(r"stickers/(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{15,})", text)
    if m:
        return int(m.group(1))
    return None


def extract_emoji(text):
    if not text:
        return None
    text = text.strip()
    import re
    m = re.match(r"<a?:\w+:(\d+)>", text)
    if m:
        return m.group(0)
    if text.isdigit():
        return text
    if len(text) <= 4:
        return text
    m = re.search(r"(\d{15,})", text)
    if m:
        return m.group(0)
    return text


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


async def respond(ctx_or_interaction, embed=None, content=None):
    if isinstance(ctx_or_interaction, commands.Context):
        await ctx_or_interaction.send(embed=embed, content=content)
    else:
        if not ctx_or_interaction.response.is_done():
            await ctx_or_interaction.response.send_message(embed=embed, content=content)
        else:
            await ctx_or_interaction.followup.send(embed=embed, content=content)


class Welcome(commands.Cog, name="welcome"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

    def get_config(self, guild_id):
        defaults = {"channel": None, "message": "Welcome {member} to **{server}**!", "autorole": None, "image": None, "leave_channel": None, "leave_message": "Goodbye {member}! We'll miss you.", "sticker": None, "emoji": None}
        stored = self.data.get(str(guild_id), {})
        return {**defaults, **stored}

    async def _setleavechannel(self, ctx, channel):
        if channel is None:
            return await respond(ctx, content="Please specify a leave channel.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {}
        self.data[gid]["leave_channel"] = channel.id
        save_data(self.data)
        await respond(ctx, content=f"Leave channel set to {channel.mention}.")

    @commands.command(name="setleavechannel")
    @commands.has_permissions(administrator=True)
    async def setleavechannel_prefix(self, ctx, channel: discord.TextChannel = None):
        await self._setleavechannel(ctx, channel)

    @app_commands.command(name="setleavechannel", description="Set the leave (goodbye) channel")
    @app_commands.default_permissions(administrator=True)
    async def setleavechannel_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._setleavechannel(interaction, channel)

    async def _setleavemsg(self, ctx, *, message):
        if not message:
            return await respond(ctx, content="Please provide a leave message.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {}
        self.data[gid]["leave_message"] = message
        save_data(self.data)
        await respond(ctx, content="Leave message updated!")

    @commands.command(name="setleavemsg")
    @commands.has_permissions(administrator=True)
    async def setleavemsg_prefix(self, ctx, *, message):
        await self._setleavemsg(ctx, message=message)

    @app_commands.command(name="setleavemsg", description="Set the leave (goodbye) message")
    @app_commands.default_permissions(administrator=True)
    async def setleavemsg_slash(self, interaction: discord.Interaction, message: str):
        await self._setleavemsg(interaction, message=message)

    async def _setwelcome(self, ctx, channel):
        if channel is None:
            return await respond(ctx, content="Please specify a welcome channel.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {"channel": None, "message": "Welcome {member} to **{server}**!", "autorole": None, "image": None}
        self.data[gid]["channel"] = channel.id
        save_data(self.data)
        await respond(ctx, content=f"Welcome channel set to {channel.mention}.")

    @commands.command(name="setwelcome")
    @commands.has_permissions(administrator=True)
    async def setwelcome_prefix(self, ctx, channel: discord.TextChannel = None):
        await self._setwelcome(ctx, channel)

    @app_commands.command(name="setwelcome", description="Set the welcome channel")
    @app_commands.default_permissions(administrator=True)
    async def setwelcome_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._setwelcome(interaction, channel)

    async def _setwelcomemsg(self, ctx, *, message):
        if not message:
            return await respond(ctx, content="Please provide a welcome message.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {"channel": None, "message": "Welcome {member} to **{server}**!", "autorole": None, "image": None}
        self.data[gid]["message"] = message
        save_data(self.data)
        await respond(ctx, content="Welcome message updated!")

    @commands.command(name="setwelcomemsg")
    @commands.has_permissions(administrator=True)
    async def setwelcomemsg_prefix(self, ctx, *, message):
        await self._setwelcomemsg(ctx, message=message)

    @app_commands.command(name="setwelcomemsg", description="Set the welcome message")
    @app_commands.default_permissions(administrator=True)
    async def setwelcomemsg_slash(self, interaction: discord.Interaction, message: str):
        await self._setwelcomemsg(interaction, message=message)

    async def _setwelcomesticker(self, ctx, sticker_input):
        sticker_id = extract_sticker_id(sticker_input)
        if not sticker_id:
            return await respond(ctx, content="Please provide a valid sticker ID or sticker URL.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {"channel": None, "message": "Welcome {member} to **{server}**!", "autorole": None, "image": None}
        self.data[gid]["sticker"] = sticker_id
        save_data(self.data)
        await respond(ctx, content=f"Welcome sticker set to `{sticker_id}`.")

    @commands.command(name="setwelcomesticker")
    @commands.has_permissions(administrator=True)
    async def setwelcomesticker_prefix(self, ctx, *, sticker: str = None):
        await self._setwelcomesticker(ctx, sticker)

    @app_commands.command(name="setwelcomesticker", description="Set a sticker to send with the welcome message (ID or URL)")
    @app_commands.default_permissions(administrator=True)
    async def setwelcomesticker_slash(self, interaction: discord.Interaction, sticker: str):
        await self._setwelcomesticker(interaction, sticker)

    async def _setwelcomeemoji(self, ctx, emoji_input):
        emoji = extract_emoji(emoji_input)
        if not emoji:
            return await respond(ctx, content="Please provide a valid emoji (custom `<:name:id>` or unicode).")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {"channel": None, "message": "Welcome {member} to **{server}**!", "autorole": None, "image": None}
        self.data[gid]["emoji"] = emoji
        save_data(self.data)
        await respond(ctx, content=f"Welcome emoji set to {emoji}")

    @commands.command(name="setwelcomeemoji")
    @commands.has_permissions(administrator=True)
    async def setwelcomeemoji_prefix(self, ctx, *, emoji: str = None):
        await self._setwelcomeemoji(ctx, emoji)

    @app_commands.command(name="setwelcomeemoji", description="Set an emoji to send with the welcome message")
    @app_commands.default_permissions(administrator=True)
    async def setwelcomeemoji_slash(self, interaction: discord.Interaction, emoji: str):
        await self._setwelcomeemoji(interaction, emoji)

    async def _setautorole(self, ctx, role):
        if role is None:
            return await respond(ctx, content="Please specify a role.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {"channel": None, "message": "Welcome {member} to **{server}**!", "autorole": None, "image": None}
        self.data[gid]["autorole"] = role.id
        save_data(self.data)
        await respond(ctx, content=f"Auto-role set to {role.mention}.")

    async def _setwelcomeimage(self, ctx, url):
        if not url:
            return await respond(ctx, content="Please provide an image URL.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {"channel": None, "message": "Welcome {member} to **{server}**!", "autorole": None, "image": None}
        self.data[gid]["image"] = url
        save_data(self.data)
        await respond(ctx, content="Welcome image set!")

    @commands.command(name="setwelcomeimage")
    @commands.has_permissions(administrator=True)
    async def setwelcomeimage_prefix(self, ctx, *, url=None):
        await self._setwelcomeimage(ctx, url)

    @app_commands.command(name="setwelcomeimage", description="Set a banner image for welcome messages")
    @app_commands.default_permissions(administrator=True)
    async def setwelcomeimage_slash(self, interaction: discord.Interaction, url: str):
        await self._setwelcomeimage(interaction, url)

    @commands.command(name="setautorole")
    @commands.has_permissions(administrator=True)
    async def setautorole_prefix(self, ctx, role: discord.Role = None):
        await self._setautorole(ctx, role)

    @app_commands.command(name="setautorole", description="Set a role to give new members")
    @app_commands.default_permissions(administrator=True)
    async def setautorole_slash(self, interaction: discord.Interaction, role: discord.Role):
        await self._setautorole(interaction, role)

    async def _testwelcome(self, ctx):
        config = self.get_config(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if not config["channel"]:
            return await respond(ctx, content="Welcome channel not set.")
        mention = ctx.user.mention if isinstance(ctx, discord.Interaction) else ctx.author.mention
        msg = config["message"].replace("{member}", mention).replace("{user}", mention).replace("{server}", ctx.guild.name)
        if config.get("emoji"):
            msg = f"{config['emoji']} {msg}"
        embed = discord.Embed(description=msg, color=discord.Color.green())
        embed.set_author(name=f"Welcome to {ctx.guild.name}!", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        if config.get("image"):
            embed.set_image(url=config["image"])
        channel = ctx.guild.get_channel(config["channel"])
        if channel:
            kwargs = {"embed": embed}
            if config.get("sticker"):
                kwargs["stickers"] = [discord.Object(id=config["sticker"])]
            try:
                await channel.send(**kwargs)
            except discord.HTTPException as e:
                if config.get("sticker"):
                    await channel.send(embed=embed)
                    await respond(ctx, content=f"Sent test welcome (sticker failed: `{e}` — sticker may be deleted).")
                    return
                raise
            await respond(ctx, content=f"Sent test welcome to {channel.mention}.")
        else:
            await respond(ctx, content="Welcome channel not found.")

    @commands.command(name="testwelcome")
    @commands.has_permissions(administrator=True)
    async def testwelcome_prefix(self, ctx):
        await self._testwelcome(ctx)

    @app_commands.command(name="testwelcome", description="Test the welcome message")
    @app_commands.default_permissions(administrator=True)
    async def testwelcome_slash(self, interaction: discord.Interaction):
        await self._testwelcome(interaction)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        config = self.get_config(member.guild.id)
        if config["autorole"]:
            role = member.guild.get_role(config["autorole"])
            if role:
                try:
                    await member.add_roles(role)
                except:
                    pass
        if config["channel"]:
            channel = member.guild.get_channel(config["channel"])
            if channel:
                msg = config["message"].replace("{member}", member.mention).replace("{user}", member.mention).replace("{server}", member.guild.name)
                if config.get("emoji"):
                    msg = f"{config['emoji']} {msg}"
                embed = discord.Embed(description=msg, color=discord.Color.green())
                embed.set_author(name=f"Welcome to {member.guild.name}!", icon_url=member.guild.icon.url if member.guild.icon else None)
                embed.set_thumbnail(url=member.display_avatar.url)
                if config.get("image"):
                    embed.set_image(url=config["image"])
                kwargs = {"embed": embed}
                if config.get("sticker"):
                    kwargs["stickers"] = [discord.Object(id=config["sticker"])]
                try:
                    await channel.send(**kwargs)
                except discord.HTTPException:
                    if config.get("sticker"):
                        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        config = self.get_config(member.guild.id)
        if not config["leave_channel"]:
            return
        channel = member.guild.get_channel(config["leave_channel"])
        if not channel:
            return
        msg = config["leave_message"].replace("{member}", member.mention).replace("{user}", str(member)).replace("{server}", member.guild.name)
        embed = discord.Embed(description=msg, color=discord.Color.dark_red())
        embed.set_author(name=f"Goodbye from {member.guild.name}!", icon_url=member.guild.icon.url if member.guild.icon else None)
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Welcome(bot))
