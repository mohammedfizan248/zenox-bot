import discord
from discord import app_commands
from discord.ext import commands


class Admin(commands.Cog, name="admin"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="reload")
    @commands.is_owner()
    async def reload_prefix(self, ctx, cog: str = None):
        if cog:
            try:
                await self.bot.reload_extension(f"cogs.{cog}")
                await ctx.send(f"✅ Reloaded `{cog}`.")
            except Exception as e:
                await ctx.send(f"❌ Error: {e}")
        else:
            msg = []
            for ext in list(self.bot.extensions):
                try:
                    await self.bot.reload_extension(ext)
                    msg.append(f"✅ {ext}")
                except Exception as e:
                    msg.append(f"❌ {ext}: {e}")
            await ctx.send("\n".join(msg))

    @app_commands.command(name="reload", description="Reload a cog or all cogs")
    @app_commands.default_permissions(administrator=True)
    async def reload_slash(self, interaction: discord.Interaction, cog: str = None):
        await interaction.response.defer(ephemeral=True)
        if cog:
            try:
                await self.bot.reload_extension(f"cogs.{cog}")
                await interaction.followup.send(f"✅ Reloaded `{cog}`.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
        else:
            msg = []
            for ext in list(self.bot.extensions):
                try:
                    await self.bot.reload_extension(ext)
                    msg.append(f"✅ {ext}")
                except Exception as e:
                    msg.append(f"❌ {ext}: {e}")
            await interaction.followup.send("\n".join(msg), ephemeral=True)

    @commands.command(name="guilds")
    @commands.is_owner()
    async def guilds_prefix(self, ctx):
        guilds = "\n".join(f"{g.name} ({g.id}) - {g.member_count} members" for g in self.bot.guilds)
        await ctx.send(f"**Servers ({len(self.bot.guilds)}):**\n{guilds}")

    @app_commands.command(name="guilds", description="List all guilds the bot is in")
    @app_commands.default_permissions(administrator=True)
    async def guilds_slash(self, interaction: discord.Interaction):
        guilds = "\n".join(f"{g.name} ({g.id}) - {g.member_count} members" for g in self.bot.guilds)
        await interaction.response.send_message(f"**Servers ({len(self.bot.guilds)}):**\n{guilds}", ephemeral=True)

    @commands.command(name="say")
    @commands.is_owner()
    async def say_prefix(self, ctx, *, message):
        embed = discord.Embed(description=message, color=discord.Color.blue())
        embed.set_footer(text="- ZX MANAGEMENT")
        await ctx.send(embed=embed)
        try:
            await ctx.message.delete()
        except:
            pass

    @app_commands.command(name="say", description="Make the bot say a message")
    @app_commands.default_permissions(administrator=True)
    async def say_slash(self, interaction: discord.Interaction, message: str):
        embed = discord.Embed(description=message, color=discord.Color.blue())
        embed.set_footer(text="- ZX MANAGEMENT")
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Message sent.", ephemeral=True)

    async def _dm(self, ctx, member, message):
        if member is None:
            return await ctx.send("Please specify a member.")
        if not message:
            return await ctx.send("Please provide a message.")
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        try:
            embed = discord.Embed(description=message, color=discord.Color.blue())
            embed.set_author(name=f"Message from {author}", icon_url=author.display_avatar.url)
            embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            await member.send(embed=embed)
            await ctx.send(f"✅ DM sent to {member.mention}.")
        except discord.Forbidden:
            await ctx.send(f"❌ Could not DM {member.mention} — they have DMs disabled.")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="dm")
    @commands.has_permissions(manage_messages=True)
    async def dm_prefix(self, ctx, member: discord.Member = None, *, message=None):
        await self._dm(ctx, member, message)

    @app_commands.command(name="dm", description="DM a member through the bot")
    @app_commands.default_permissions(manage_messages=True)
    async def dm_slash(self, interaction: discord.Interaction, member: discord.Member, message: str):
        await self._dm(interaction, member, message)


async def setup(bot):
    await bot.add_cog(Admin(bot))
