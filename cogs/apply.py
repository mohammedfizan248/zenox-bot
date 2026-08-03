import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
import datetime
import re

DATA_FILE = "data/applications.json"


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


QUESTIONS_DEFAULT = [
    "What is your in-game name?",
    "How old are you?",
    "Why do you want to play as a bot?",
    "Do you understand the server bot rules?",
    "What roleplay experience do you have?",
    "How many hours can you play per week?",
    "What will your bot character do in-game?",
    "Will you always stay in character as a bot?",
    "What will you do if someone asks you to break character?",
    "Do you agree to follow all ZENOX ROLEPLAY server rules?",
]


class ApplyModal(discord.ui.Modal, title="Bot Application"):
    def __init__(self, questions, channel, page=0, answers=None):
        super().__init__(timeout=None)
        self.questions = questions
        self.channel = channel
        self.page = page
        self.answers = answers or {}
        page_qs = questions[page * 5 : (page + 1) * 5]
        self.inputs = []
        for i, q in enumerate(page_qs):
            inp = discord.ui.TextInput(label=q[:45], style=discord.TextStyle.paragraph if len(q) > 50 else discord.TextStyle.short, required=True, max_length=500, custom_id=f"p{page}_q{i}")
            self.inputs.append(inp)
            self.add_item(inp)

    async def on_submit(self, interaction: discord.Interaction):
        self.answers.update({f"q_{self.page * 5 + i}": inp.value for i, inp in enumerate(self.inputs)})
        if (self.page + 1) * 5 < len(self.questions):
            await interaction.response.send_modal(ApplyModal(self.questions, self.channel, page=self.page + 1, answers=self.answers))
            return
        data = load_data()
        gid = str(interaction.guild.id)
        if gid not in data:
            data[gid] = {"channel": None, "questions": QUESTIONS_DEFAULT, "apps": {}}
        config = data[gid]
        app_id = str(len(config["apps"]) + 1)
        config["apps"][app_id] = {
            "user": interaction.user.id,
            "user_name": str(interaction.user),
            "answers": self.answers,
            "status": "pending",
            "time": discord.utils.utcnow().isoformat(),
        }
        save_data(data)
        embed = discord.Embed(title=f"New Bot Application #{app_id}", color=discord.Color.blue())
        embed.add_field(name="Applicant", value=interaction.user.mention)
        embed.add_field(name="Status", value="Pending")
        embed.add_field(name="Submitted", value=discord.utils.utcnow().strftime("%b %d, %Y %H:%M UTC"))
        for i, q in enumerate(self.questions):
            embed.add_field(name=q, value=self.answers.get(f"q_{i}", "No answer"), inline=False)
        view = AppReviewView(gid, app_id)
        target = self.channel or interaction.channel
        await target.send(embed=embed, view=view)
        await interaction.response.send_message("Your bot application has been submitted! Staff will review it shortly.", ephemeral=True)


class ApplyPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply Now", style=discord.ButtonStyle.primary, emoji="🤖", custom_id="apply_panel")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = str(interaction.guild.id)
        data = load_data()
        if gid not in data:
            data[gid] = {"channel": None, "questions": QUESTIONS_DEFAULT, "apps": {}}
            save_data(data)
        config = data[gid]
        questions = config.get("questions", QUESTIONS_DEFAULT)
        channel = None
        ch_id = config.get("channel")
        if ch_id:
            ch = interaction.guild.get_channel(ch_id)
            if ch:
                channel = ch
        await interaction.response.send_modal(ApplyModal(questions, channel))


class AppReviewView(discord.ui.View):
    def __init__(self, guild_id=None, app_id=None):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.app_id = app_id

    def _resolve(self, interaction):
        if self.guild_id is not None and self.app_id is not None:
            return str(self.guild_id), str(self.app_id)
        gid = str(interaction.guild.id)
        app_id = None
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed and embed.title:
            m = re.search(r"#(\d+)", embed.title)
            if m:
                app_id = m.group(1)
        return gid, app_id

    async def _load_app(self, interaction):
        gid, app_id = self._resolve(interaction)
        if not app_id:
            return None, None, None
        data = load_data()
        app = data.get(gid, {}).get("apps", {}).get(app_id)
        return data, app, app_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="✅", custom_id="accept_app")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.user.guild_permissions.administrator:
                return await interaction.response.send_message("Only admins can review applications.", ephemeral=True)
            data, app, app_id = await self._load_app(interaction)
            if not app:
                return await interaction.response.send_message("Application not found.", ephemeral=True)
            if app["status"] != "pending":
                return await interaction.response.send_message("This application was already reviewed.", ephemeral=True)
            app["status"] = "accepted"
            app["reviewer"] = interaction.user.id
            save_data(data)
            member = interaction.guild.get_member(app["user"])
            if member:
                try:
                    await member.send(f"🎉 Your bot application **#{app_id}** has been **accepted** in **{interaction.guild.name}**! Welcome to the server!")
                except:
                    pass
            embed = discord.Embed(title=f"Bot Application #{app_id} - Accepted", color=discord.Color.green())
            embed.add_field(name="Applicant", value=f"<@{app['user']}>")
            embed.add_field(name="Reviewed by", value=interaction.user.mention)
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌", custom_id="deny_app")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.user.guild_permissions.administrator:
                return await interaction.response.send_message("Only admins can review applications.", ephemeral=True)
            data, app, app_id = await self._load_app(interaction)
            if not app:
                return await interaction.response.send_message("Application not found.", ephemeral=True)
            if app["status"] != "pending":
                return await interaction.response.send_message("This application was already reviewed.", ephemeral=True)
            app["status"] = "denied"
            app["reviewer"] = interaction.user.id
            save_data(data)
            member = interaction.guild.get_member(app["user"])
            if member:
                try:
                    await member.send(f"Your bot application **#{app_id}** in **{interaction.guild.name}** has been **denied**.")
                except:
                    pass
            embed = discord.Embed(title=f"Bot Application #{app_id} - Denied", color=discord.Color.red())
            embed.add_field(name="Applicant", value=f"<@{app['user']}>")
            embed.add_field(name="Reviewed by", value=interaction.user.mention)
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Error: `{e}`", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Error: `{e}`", ephemeral=True)


class Apply(commands.Cog, name="apply"):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(ApplyPanelView())
        self.bot.add_view(AppReviewView())

    def _is_admin(self, ctx):
        user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
        return user.guild_permissions.administrator

    async def _setapplychannel(self, ctx, channel):
        if channel is None:
            return await respond(ctx, content="Please specify a channel.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        data = load_data()
        if gid not in data:
            data[gid] = {"channel": None, "questions": QUESTIONS_DEFAULT, "apps": {}}
        data[gid]["channel"] = channel.id
        save_data(data)
        embed = discord.Embed(
            title="🤖 Bot Application",
            description="Interested in playing as a bot in ZENOX ROLEPLAY? Click the button below to submit your application.",
            color=discord.Color.blue(),
        )
        await channel.send(embed=embed, view=ApplyPanelView())
        await respond(ctx, content=f"Application channel set to {channel.mention}. Application panel sent.")

    @commands.command(name="setapplychannel")
    @commands.has_permissions(administrator=True)
    async def setapplychannel_prefix(self, ctx, channel: discord.TextChannel = None):
        await self._setapplychannel(ctx, channel)

    @app_commands.command(name="setapplychannel", description="Set the channel for application submissions")
    async def setapplychannel_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
        await self._setapplychannel(interaction, channel)

    async def _setapplyquestions(self, ctx, questions):
        if not questions:
            return await respond(ctx, content="Please provide questions separated by `|`.")
        qlist = [q.strip() for q in questions.split("|") if q.strip()]
        if len(qlist) < 1:
            return await respond(ctx, content="At least 1 question is required.")
        if len(qlist) > 10:
            return await respond(ctx, content="Maximum 10 questions allowed (5 per form page).")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        data = load_data()
        if gid not in data:
            data[gid] = {"channel": None, "questions": QUESTIONS_DEFAULT, "apps": {}}
        data[gid]["questions"] = qlist
        save_data(data)
        await respond(ctx, content=f"Application questions set to:\n" + "\n".join(f"{i+1}. {q}" for i, q in enumerate(qlist)))

    @commands.command(name="setapplyquestions")
    @commands.has_permissions(administrator=True)
    async def setapplyquestions_prefix(self, ctx, *, questions):
        await self._setapplyquestions(ctx, questions)

    @app_commands.command(name="setapplyquestions", description="Set application questions (separate with |)")
    async def setapplyquestions_slash(self, interaction: discord.Interaction, q1: str, q2: str = None, q3: str = None, q4: str = None, q5: str = None, q6: str = None, q7: str = None, q8: str = None, q9: str = None, q10: str = None):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
        qs = [q for q in [q1, q2, q3, q4, q5, q6, q7, q8, q9, q10] if q]
        await self._setapplyquestions(interaction, "|".join(qs))

    async def _apply_prefix(self, ctx):
        gid = str(ctx.guild.id)
        data = load_data()
        if gid not in data:
            data[gid] = {"channel": None, "questions": QUESTIONS_DEFAULT, "apps": {}}
            save_data(data)
        config = data[gid]
        questions = config.get("questions", QUESTIONS_DEFAULT)
        author = ctx.author
        await ctx.send(f"{author.mention} check your DMs to start the application!")
        try:
            await author.send("**Bot Application**\nAnswer the following questions. Type `cancel` at any time to quit.")
        except discord.Forbidden:
            return await ctx.send("I can't DM you! Enable DMs and try again.")
        answers = {}
        for i, q in enumerate(questions):
            await author.send(f"**Question {i+1}/{len(questions)}:** {q}")
            def check(m):
                return m.author == author and m.channel == author.dm_channel
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=300)
            except asyncio.TimeoutError:
                return await author.send("Application timed out.")
            if msg.content.lower() == "cancel":
                return await author.send("Application cancelled.")
            answers[f"q_{i}"] = msg.content
        app_id = str(len(config["apps"]) + 1)
        config["apps"][app_id] = {
            "user": author.id,
            "user_name": str(author),
            "answers": answers,
            "status": "pending",
            "time": discord.utils.utcnow().isoformat(),
        }
        save_data(data)
        await author.send(f"✅ Whitelist application **#{app_id}** submitted! Staff will review it shortly.")
        embed = discord.Embed(title=f"New Bot Application #{app_id}", color=discord.Color.blue())
        embed.add_field(name="Applicant", value=author.mention)
        embed.add_field(name="Status", value="Pending")
        embed.add_field(name="Submitted", value=discord.utils.utcnow().strftime("%b %d, %Y %H:%M UTC"))
        for i, q in enumerate(questions):
            embed.add_field(name=q, value=answers.get(f"q_{i}", "No answer"), inline=False)
        view = AppReviewView(gid, app_id)
        target = ctx.guild.get_channel(config["channel"]) if config.get("channel") else ctx.channel
        if target is None:
            target = ctx.channel
        await target.send(embed=embed, view=view)

    @commands.command(name="apply")
    async def apply_prefix(self, ctx):
        await self._apply_prefix(ctx)

    @app_commands.command(name="apply", description="Submit a bot application")
    async def apply_slash(self, interaction: discord.Interaction):
        gid = str(interaction.guild.id)
        data = load_data()
        if gid not in data:
            data[gid] = {"channel": None, "questions": QUESTIONS_DEFAULT, "apps": {}}
            save_data(data)
        questions = data[gid].get("questions", QUESTIONS_DEFAULT)
        await interaction.response.send_modal(ApplyModal(questions, interaction.channel))

    async def _accept(self, ctx, member, app_id):
        if member is None:
            return await respond(ctx, content="Please specify a member to accept.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        data = load_data()
        if gid not in data:
            return await respond(ctx, content="No applications found.")
        target = None
        target_id = None
        if app_id:
            app = data[gid]["apps"].get(app_id)
            if app:
                target = app
                target_id = app_id
        if not target:
            for aid, app in data[gid]["apps"].items():
                if app["user"] == member.id and app["status"] == "pending":
                    target = app
                    target_id = aid
                    break
        if not target:
            return await respond(ctx, content="No pending application found for that member.")
        target["status"] = "accepted"
        target["reviewer"] = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        save_data(data)
        try:
            await member.send(f"🎉 Your bot application **#{target_id}** has been **accepted** in **{ctx.guild.name}**! Welcome to the server!")
        except:
            pass
        await respond(ctx, content=f"Accepted application #{target_id} for {member.mention}.")

    @commands.command(name="accept")
    @commands.has_permissions(administrator=True)
    async def accept_prefix(self, ctx, member: discord.Member = None, app_id: str = None):
        await self._accept(ctx, member, app_id)

    @app_commands.command(name="accept", description="Accept a bot application")
    async def accept_slash(self, interaction: discord.Interaction, member: discord.Member, application_id: str = None):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
        await self._accept(interaction, member, application_id)

    async def _deny(self, ctx, member, reason, app_id):
        if member is None:
            return await respond(ctx, content="Please specify a member to deny.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        data = load_data()
        if gid not in data:
            return await respond(ctx, content="No applications found.")
        target = None
        target_id = None
        if app_id:
            app = data[gid]["apps"].get(app_id)
            if app:
                target = app
                target_id = app_id
        if not target:
            for aid, app in data[gid]["apps"].items():
                if app["user"] == member.id and app["status"] == "pending":
                    target = app
                    target_id = aid
                    break
        if not target:
            return await respond(ctx, content="No pending application found for that member.")
        target["status"] = "denied"
        target["reviewer"] = ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id
        save_data(data)
        try:
            msg = f"Your bot application **#{target_id}** in **{ctx.guild.name}** has been **denied**."
            if reason:
                msg += f"\nReason: {reason}"
            await member.send(msg)
        except:
            pass
        await respond(ctx, content=f"Denied application #{target_id} for {member.mention}.")

    @commands.command(name="deny")
    @commands.has_permissions(administrator=True)
    async def deny_prefix(self, ctx, member: discord.Member = None, app_id: str = None, *, reason="No reason provided"):
        await self._deny(ctx, member, reason, app_id)

    @app_commands.command(name="deny", description="Deny a bot application")
    async def deny_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", application_id: str = None):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
        await self._deny(interaction, member, reason, application_id)

    async def _applications(self, ctx, status):
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        data = load_data()
        if gid not in data or not data[gid].get("apps"):
            return await respond(ctx, content="No applications found.")
        apps = data[gid]["apps"]
        if status and status != "all":
            filtered = {aid: a for aid, a in apps.items() if a["status"] == status}
        else:
            filtered = apps
        if not filtered:
            return await respond(ctx, content=f"No {status or ''} applications found.")
        embed = discord.Embed(title=f"Applications ({status or 'all'})", color=discord.Color.blue())
        for aid, a in list(filtered.items())[:10]:
            embed.add_field(name=f"#{aid} - {a['user_name']}", value=f"Status: {a['status']}\n<@{a['user']}>", inline=False)
        if len(filtered) > 10:
            embed.set_footer(text=f"+ {len(filtered) - 10} more")
        await respond(ctx, embed=embed)

    @commands.command(name="applications")
    @commands.has_permissions(administrator=True)
    async def applications_prefix(self, ctx, status: str = "pending"):
        await self._applications(ctx, status)

    @app_commands.command(name="applications", description="List applications by status (pending/accepted/denied/all)")
    async def applications_slash(self, interaction: discord.Interaction, status: str = "pending"):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
        await self._applications(interaction, status)

    @app_commands.command(name="application", description="List applications by status (alias of /applications)")
    async def application_slash(self, interaction: discord.Interaction, status: str = "pending"):
        if not self._is_admin(interaction):
            return await interaction.response.send_message("Only administrators can use this command.", ephemeral=True)
        await self._applications(interaction, status)


async def setup(bot):
    await bot.add_cog(Apply(bot))
