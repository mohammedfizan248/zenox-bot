import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
import json
import os
import datetime

DATA_FILE = "data/tickets.json"


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


class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green, emoji="🎫", custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        config = Tickets.get_config_for(guild.id)
        cat_id = config.get("category")
        category = guild.get_channel(cat_id) if cat_id else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }
        channel_name = f"ticket-{interaction.user.name.lower().replace(' ', '-')}"
        existing = discord.utils.get(guild.text_channels, name=channel_name)
        if existing:
            return await interaction.response.send_message("You already have an open ticket!", ephemeral=True)
        channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
        embed = discord.Embed(title="Ticket Created", description=f"Support will be with you shortly, {interaction.user.mention}.", color=discord.Color.green())
        close_view = CloseView(interaction.user.id)
        await channel.send(embed=embed, view=close_view)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)
        cid = str(channel.id)
        data = load_data()
        if str(guild.id) not in data:
            data[str(guild.id)] = {}
        data[str(guild.id)][cid] = {"owner": interaction.user.id, "created": discord.utils.utcnow().isoformat()}
        save_data(data)


class CloseView(View):
    def __init__(self, owner_id):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.owner_id and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Only the ticket owner or a moderator can close this.", ephemeral=True)
        guild = interaction.guild
        prompts = []
        close_conf = TicketCloseView(guild, interaction.channel, interaction.user)
        await interaction.response.send_message("Are you sure you want to close this ticket?", view=close_conf, ephemeral=True)


class TicketCloseView(View):
    def __init__(self, guild, channel, user):
        super().__init__(timeout=30)
        self.guild = guild
        self.channel = channel
        self.user = user

    @discord.ui.button(label="Yes, Close", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("This is not your prompt.", ephemeral=True)
        await interaction.response.defer()
        try:
            transcript = []
            async for msg in self.channel.history(limit=500):
                transcript.append(f"[{msg.created_at}] {msg.author.name}: {msg.clean_content}")
            transcript_text = "\n".join(reversed(transcript))
            ts_path = f"data/transcripts/{self.channel.id}.txt"
            os.makedirs(os.path.dirname(ts_path), exist_ok=True)
            with open(ts_path, "w", encoding="utf-8") as f:
                f.write(transcript_text)
            data = load_data()
            gid = str(self.guild.id)
            cid = str(self.channel.id)
            if gid in data and cid in data[gid]:
                del data[gid][cid]
                save_data(data)
        except:
            pass
        await self.channel.delete()
        await interaction.followup.send(f"Ticket ({self.channel.name}) closed.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("This is not your prompt.", ephemeral=True)
        await interaction.response.edit_message(content="Ticket closure cancelled.", view=None)


class Tickets(commands.Cog, name="tickets"):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TicketView())
        self.data = load_data()

    @staticmethod
    def get_config_for(guild_id):
        data = load_data()
        gid = str(guild_id)
        if gid not in data:
            data[gid] = {}
        return data[gid].get("_config", {"category": None})

    async def _settickets(self, ctx, category):
        if category is None:
            return await respond(ctx, content="Please specify a category.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = {}
        if "_config" not in self.data[gid]:
            self.data[gid]["_config"] = {}
        self.data[gid]["_config"]["category"] = category.id
        save_data(self.data)
        embed = discord.Embed(title="🎫 Support Tickets", description="Click the button below to create a support ticket.", color=discord.Color.blue())
        embed.set_footer(text=f"{ctx.guild.name} Support")
        view = TicketView()
        channel = ctx.channel
        if isinstance(ctx, discord.Interaction):
            await channel.send(embed=embed, view=view)
            await ctx.response.send_message(f"Ticket panel sent to {channel.mention}.", ephemeral=True)
        else:
            await channel.send(embed=embed, view=view)
            await ctx.send(f"Ticket panel sent to {channel.mention}.")

    @commands.command(name="settickets")
    @commands.has_permissions(administrator=True)
    async def settickets_prefix(self, ctx, category: discord.CategoryChannel = None):
        await self._settickets(ctx, category)

    @app_commands.command(name="settickets", description="Set the ticket category and send the ticket panel")
    @app_commands.default_permissions(administrator=True)
    async def settickets_slash(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await self._settickets(interaction, category)

    async def _adduser(self, ctx, member):
        if member is None:
            return await respond(ctx, content="Please specify a member.")
        channel = ctx.channel
        if "ticket-" not in channel.name:
            return await respond(ctx, content="This is not a ticket channel.")
        await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await respond(ctx, content=f"Added {member.mention} to the ticket.")

    @commands.command(name="adduser")
    @commands.has_permissions(manage_channels=True)
    async def adduser_prefix(self, ctx, member: discord.Member = None):
        await self._adduser(ctx, member)

    @app_commands.command(name="adduser", description="Add a user to the ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def adduser_slash(self, interaction: discord.Interaction, member: discord.Member):
        await self._adduser(interaction, member)

    async def _removeuser(self, ctx, member):
        if member is None:
            return await respond(ctx, content="Please specify a member.")
        channel = ctx.channel
        if "ticket-" not in channel.name:
            return await respond(ctx, content="This is not a ticket channel.")
        await channel.set_permissions(member, overwrite=None)
        await respond(ctx, content=f"Removed {member.mention} from the ticket.")

    @commands.command(name="removeuser")
    @commands.has_permissions(manage_channels=True)
    async def removeuser_prefix(self, ctx, member: discord.Member = None):
        await self._removeuser(ctx, member)

    @app_commands.command(name="removeuser", description="Remove a user from the ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def removeuser_slash(self, interaction: discord.Interaction, member: discord.Member):
        await self._removeuser(interaction, member)

    async def _renovate(self, ctx):
        channel = ctx.channel
        if "ticket-" not in channel.name:
            return await respond(ctx, content="This is not a ticket channel.")
        await channel.edit(topic=f"Renovated by {ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id}")
        await respond(ctx, content="Ticket renovated.")

    @commands.command(name="renovate")
    @commands.has_permissions(manage_channels=True)
    async def renovate_prefix(self, ctx):
        await self._renovate(ctx)

    @app_commands.command(name="renovate", description="Renovate the ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def renovate_slash(self, interaction: discord.Interaction):
        await self._renovate(interaction)

    async def _transcript(self, ctx):
        channel = ctx.channel
        if "ticket-" not in channel.name:
            return await respond(ctx, content="This is not a ticket channel.")
        await respond(ctx, content="Generating transcript...")
        transcript = []
        async for msg in channel.history(limit=500):
            transcript.append(f"[{msg.created_at}] {msg.author.name}: {msg.clean_content}")
        ts_path = f"data/transcripts/{channel.id}.txt"
        os.makedirs(os.path.dirname(ts_path), exist_ok=True)
        with open(ts_path, "w", encoding="utf-8") as f:
            f.write("\n".join(reversed(transcript)))
        await respond(ctx, content=f"Transcript saved as `{ts_path}`.")

    @commands.command(name="transcript")
    @commands.has_permissions(manage_channels=True)
    async def transcript_prefix(self, ctx):
        await self._transcript(ctx)

    @app_commands.command(name="transcript", description="Save a transcript of the ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def transcript_slash(self, interaction: discord.Interaction):
        await self._transcript(interaction)


async def setup(bot):
    await bot.add_cog(Tickets(bot))
