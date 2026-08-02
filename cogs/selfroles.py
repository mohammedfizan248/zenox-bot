import discord
from discord import app_commands
from discord.ext import commands
import json
import os

DATA_FILE = "data/selfroles.json"


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


class SelfRoleButton(discord.ui.Button):
    def __init__(self, role_id, role_name):
        super().__init__(style=discord.ButtonStyle.primary, label=role_name, custom_id=f"selfrole_{role_id}")

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.custom_id.split("_")[1]))
        if role is None:
            return await interaction.response.send_message("That role no longer exists.", ephemeral=True)
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("I can't manage that role (it's above my highest role).", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Self role removed")
            await interaction.response.send_message(f"Removed {role.mention} from you.", ephemeral=True)
        else:
            await interaction.user.add_roles(role, reason="Self role added")
            await interaction.response.send_message(f"Added {role.mention} to you!", ephemeral=True)


class ChannelLinkButton(discord.ui.Button):
    def __init__(self, channel):
        super().__init__(style=discord.ButtonStyle.link, label=f"Open {channel.name}", url=channel.jump_url)


class SelfRoleView(discord.ui.View):
    def __init__(self, roles, channel_link=None):
        super().__init__(timeout=None)
        if channel_link is not None:
            self.add_item(ChannelLinkButton(channel_link))
        for role in roles:
            self.add_item(SelfRoleButton(role["id"], role["name"]))


class SelfRoles(commands.Cog, name="selfroles"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()
        for panels in self.data.values():
            for panel in panels:
                channel_link = self.bot.get_channel(panel["channel_link"]) if panel.get("channel_link") else None
                self.bot.add_view(SelfRoleView(panel["roles"], channel_link))

    async def _setselfroles(self, ctx, channel, message, roles, image=None, channel_link=None):
        if channel is None:
            return await respond(ctx, content="Please specify a channel.")
        if not roles:
            return await respond(ctx, content="Please specify at least one role.")
        if len(roles) > 15:
            return await respond(ctx, content="Maximum 15 roles per panel.")
        embed = discord.Embed(title="🎭 Self Roles", description=message or "Click a button to get a role!", color=discord.Color.blue())
        role_list = ", ".join(r.mention for r in roles)
        embed.add_field(name="Available Roles", value=role_list, inline=False)
        embed.set_footer(text="Click a button to add/remove a role.")
        if image:
            embed.set_image(url=image)
        view = SelfRoleView([{"id": r.id, "name": r.name} for r in roles], channel_link)
        sent = await channel.send(embed=embed, view=view)
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if gid not in self.data:
            self.data[gid] = []
        self.data[gid].append({
            "channel": channel.id,
            "message": sent.id,
            "roles": [{"id": r.id, "name": r.name} for r in roles],
            "image": image,
            "channel_link": channel_link.id if channel_link else None,
        })
        save_data(self.data)
        await respond(ctx, content=f"Self-role panel sent to {channel.mention}.")

    @commands.command(name="setselfroles")
    @commands.has_permissions(administrator=True)
    async def setselfroles_prefix(self, ctx, channel: discord.TextChannel = None, *, args=None):
        roles = []
        message = "Click a button to get a role!"
        image = None
        channel_link = None
        if args:
            parts = args.split()
            quoted = None
            for part in parts:
                if part.startswith('"'):
                    quoted = part[1:]
                    continue
                if quoted is not None:
                    if part.endswith('"'):
                        message = f"{quoted} {part[:-1]}"
                        quoted = None
                    else:
                        quoted += f" {part}"
                    continue
                if part.lower().startswith(("http://", "https://")):
                    image = part
                    continue
                try:
                    role = await commands.RoleConverter().convert(ctx, part)
                    roles.append(role)
                    continue
                except:
                    pass
                try:
                    chan = await commands.TextChannelConverter().convert(ctx, part)
                    if channel_link is None:
                        channel_link = chan
                    continue
                except:
                    continue
        await self._setselfroles(ctx, channel, message, roles, image=image, channel_link=channel_link)

    @app_commands.command(name="setselfroles", description="Create a self-role panel")
    @app_commands.default_permissions(administrator=True)
    async def setselfroles_slash(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str = "Click a button to get a role!", channel_link: discord.TextChannel = None, image_url: str = None, role1: discord.Role = None, role2: discord.Role = None, role3: discord.Role = None, role4: discord.Role = None, role5: discord.Role = None, role6: discord.Role = None, role7: discord.Role = None, role8: discord.Role = None):
        roles = [r for r in [role1, role2, role3, role4, role5, role6, role7, role8] if r]
        await self._setselfroles(interaction, channel, message, roles, image=image_url, channel_link=channel_link)

    async def _removeselfroles(self, ctx, channel):
        if channel is None:
            return await respond(ctx, content="Please specify the channel with the panel.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        panels = self.data.get(gid, [])
        removed = 0
        for panel in panels[:]:
            if panel["channel"] == channel.id:
                msg = channel.get_partial_message(panel["message"])
                try:
                    await msg.delete()
                except:
                    pass
                panels.remove(panel)
                removed += 1
        if removed:
            save_data(self.data)
            await respond(ctx, content=f"Removed {removed} self-role panel(s) from {channel.mention}.")
        else:
            await respond(ctx, content="No panels found in that channel.")

    @commands.command(name="removeselfroles")
    @commands.has_permissions(administrator=True)
    async def removeselfroles_prefix(self, ctx, channel: discord.TextChannel = None):
        await self._removeselfroles(ctx, channel)

    @app_commands.command(name="removeselfroles", description="Remove self-role panels from a channel")
    @app_commands.default_permissions(administrator=True)
    async def removeselfroles_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._removeselfroles(interaction, channel)


async def setup(bot):
    await bot.add_cog(SelfRoles(bot))
