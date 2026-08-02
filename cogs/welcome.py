import discord
from discord import app_commands
from discord.ext import commands
import json
import os

DATA_FILE = "data/welcome.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


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
        defaults = {"channel": None, "message": "Welcome {member} to **{server}**!", "autorole": None, "image": None}
        stored = self.data.get(str(guild_id), {})
        return {**defaults, **stored}

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
        embed = discord.Embed(description=msg, color=discord.Color.green())
        embed.set_author(name=f"Welcome to {ctx.guild.name}!", icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        if config.get("image"):
            embed.set_image(url=config["image"])
        channel = ctx.guild.get_channel(config["channel"])
        if channel:
            await channel.send(embed=embed)
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
                embed = discord.Embed(description=msg, color=discord.Color.green())
                embed.set_author(name=f"Welcome to {member.guild.name}!", icon_url=member.guild.icon.url if member.guild.icon else None)
                embed.set_thumbnail(url=member.display_avatar.url)
                if config.get("image"):
                    embed.set_image(url=config["image"])
                await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Welcome(bot))
