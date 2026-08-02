import discord
from discord import app_commands
from discord.ext import commands
import datetime


async def respond(ctx_or_interaction, embed=None, content=None, ephemeral=False, delete_after=None):
    if isinstance(ctx_or_interaction, commands.Context):
        await ctx_or_interaction.send(embed=embed, content=content, delete_after=delete_after)
    else:
        if not ctx_or_interaction.response.is_done():
            await ctx_or_interaction.response.send_message(embed=embed, content=content, ephemeral=ephemeral)
        else:
            await ctx_or_interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral)


class Utility(commands.Cog, name="utility"):
    def __init__(self, bot):
        self.bot = bot

    # --- PING ---
    @commands.command(name="ping")
    async def ping_prefix(self, ctx):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title="Pong!", color=discord.Color.blue())
        embed.add_field(name="Latency", value=f"{latency}ms")
        await ctx.send(embed=embed)

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping_slash(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title="Pong!", color=discord.Color.blue())
        embed.add_field(name="Latency", value=f"{latency}ms")
        await interaction.response.send_message(embed=embed)

    async def _userinfo(self, ctx, member):
        member = member or (ctx.author if isinstance(ctx, commands.Context) else ctx.user)
        embed = discord.Embed(title=f"User Info - {member}", color=member.color or discord.Color.blue())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Joined", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "Unknown")
        embed.add_field(name="Registered", value=member.created_at.strftime("%b %d, %Y"))
        roles = [r.mention for r in member.roles if r != ctx.guild.default_role]
        embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles[:10]) + ("..." if len(roles) > 10 else "") or "None", inline=False)
        await respond(ctx, embed=embed)

    @commands.command(name="userinfo")
    async def userinfo_prefix(self, ctx, member: discord.Member = None):
        await self._userinfo(ctx, member)

    @app_commands.command(name="userinfo", description="Get info about a member")
    async def userinfo_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        await self._userinfo(interaction, member)

    async def _serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=f"Server Info - {guild.name}", color=discord.Color.blue())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown")
        embed.add_field(name="Members", value=guild.member_count)
        embed.add_field(name="Channels", value=f"{len(guild.text_channels)} Text | {len(guild.voice_channels)} Voice")
        embed.add_field(name="Roles", value=len(guild.roles))
        embed.add_field(name="Boost Level", value=guild.premium_tier)
        embed.add_field(name="Created", value=guild.created_at.strftime("%b %d, %Y"))
        await respond(ctx, embed=embed)

    @commands.command(name="serverinfo")
    async def serverinfo_prefix(self, ctx):
        await self._serverinfo(ctx)

    @app_commands.command(name="serverinfo", description="Get info about the server")
    async def serverinfo_slash(self, interaction: discord.Interaction):
        await self._serverinfo(interaction)

    async def _roleinfo(self, ctx, role):
        if role is None:
            return await respond(ctx, content="Please specify a role.")
        embed = discord.Embed(title=f"Role Info - {role.name}", color=role.color or discord.Color.blue())
        embed.add_field(name="ID", value=role.id)
        embed.add_field(name="Color", value=str(role.color))
        embed.add_field(name="Members", value=len(role.members))
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No")
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No")
        embed.add_field(name="Created", value=role.created_at.strftime("%b %d, %Y"))
        await respond(ctx, embed=embed)

    @commands.command(name="roleinfo")
    async def roleinfo_prefix(self, ctx, role: discord.Role = None):
        await self._roleinfo(ctx, role)

    @app_commands.command(name="roleinfo", description="Get info about a role")
    async def roleinfo_slash(self, interaction: discord.Interaction, role: discord.Role):
        await self._roleinfo(interaction, role)

    async def _avatar(self, ctx, member):
        member = member or (ctx.author if isinstance(ctx, commands.Context) else ctx.user)
        embed = discord.Embed(title=f"{member}'s Avatar", color=discord.Color.blue())
        embed.set_image(url=member.display_avatar.url)
        await respond(ctx, embed=embed)

    @commands.command(name="avatar")
    async def avatar_prefix(self, ctx, member: discord.Member = None):
        await self._avatar(ctx, member)

    @app_commands.command(name="avatar", description="Get a member's avatar")
    async def avatar_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        await self._avatar(interaction, member)

    async def _poll(self, ctx, question, *options):
        if len(options) < 2:
            return await respond(ctx, content="Please provide at least 2 options.")
        if len(options) > 10:
            return await respond(ctx, content="Maximum 10 options allowed.")
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        desc = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
        embed = discord.Embed(title=question, description=desc, color=discord.Color.blue())
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        embed.set_footer(text=f"Poll by {author}")
        poll_msg = await ctx.channel.send(embed=embed) if isinstance(ctx, commands.Context) else await interaction.channel.send(embed=embed)
        for i in range(len(options)):
            await poll_msg.add_reaction(emojis[i])
        if not isinstance(ctx, commands.Context) and not ctx.response.is_done():
            await ctx.response.send_message("Poll created!", ephemeral=True)

    @commands.command(name="poll")
    async def poll_prefix(self, ctx, question, *options):
        await self._poll(ctx, question, *options)

    @app_commands.command(name="poll", description="Create a poll")
    async def poll_slash(self, interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None, option5: str = None, option6: str = None, option7: str = None, option8: str = None, option9: str = None, option10: str = None):
        options = [o for o in [option1, option2, option3, option4, option5, option6, option7, option8, option9, option10] if o]
        await self._poll(interaction, question, *options)

    async def _remind(self, ctx, time_seconds, *, reminder):
        if time_seconds < 10:
            return await respond(ctx, content="Minimum reminder time is 10 seconds.")
        if time_seconds > 86400:
            return await respond(ctx, content="Maximum reminder time is 24 hours.")
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        await respond(ctx, content=f"Reminder set for {time_seconds} seconds!")
        await discord.utils.sleep_until(datetime.datetime.now() + datetime.timedelta(seconds=time_seconds))
        await ctx.channel.send(f"⏰ {author.mention} Reminder: {reminder}")

    @commands.command(name="remind")
    async def remind_prefix(self, ctx, time_seconds: int, *, reminder):
        await self._remind(ctx, time_seconds, reminder=reminder)

    @app_commands.command(name="remind", description="Set a reminder")
    async def remind_slash(self, interaction: discord.Interaction, time_seconds: app_commands.Range[int, 10, 86400], reminder: str):
        await self._remind(interaction, time_seconds, reminder=reminder)


async def setup(bot):
    await bot.add_cog(Utility(bot))
