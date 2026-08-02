import discord
from discord import app_commands
from discord.ext import commands
from cogs.utility import respond
import asyncio
import json
import os
import socket
import time

import config

DATA_FILE = "data/samp.json"
UPDATE_INTERVAL = 60


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _read_length_string(data, offset):
    length = int.from_bytes(data[offset:offset + 4], "big")
    offset += 4
    value = data[offset:offset + length].decode("utf-8", errors="replace")
    offset += length
    return value, offset


def parse_address(value):
    if not value:
        return None, None
    value = value.strip().strip("`")
    if ":" in value:
        host, _, port = value.rpartition(":")
        try:
            return host.strip(), int(port)
        except ValueError:
            return None, None
    return value, config.SAMP_SERVER_PORT


class SampServer:
    @staticmethod
    async def query(host, port, query_char):
        loop = asyncio.get_running_loop()
        ip = await loop.run_in_executor(None, socket.gethostbyname, host)
        ip_bytes = bytes(int(part) for part in ip.split("."))
        packet = b"SAMP" + ip_bytes + port.to_bytes(2, "big") + query_char
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        try:
            await loop.sock_sendto(sock, packet, (host, port))
            data, _ = await asyncio.wait_for(
                loop.sock_recvfrom(sock, 8192), timeout=config.SAMP_QUERY_TIMEOUT
            )
        except (asyncio.TimeoutError, OSError):
            raise ConnectionError("Server offline or unreachable")
        finally:
            sock.close()
        if not data.startswith(b"SAMP"):
            raise ConnectionError("Invalid response from server")
        return data

    @classmethod
    async def get_info(cls, host, port):
        data = await cls.query(host, port, b"i")
        offset = 11
        password = data[offset]
        offset += 1
        players = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
        max_players = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
        hostname, offset = _read_length_string(data, offset)
        gamemode, offset = _read_length_string(data, offset)
        language, offset = _read_length_string(data, offset)
        return {
            "host": host,
            "port": port,
            "password": bool(password),
            "players": players,
            "max_players": max_players,
            "hostname": hostname,
            "gamemode": gamemode,
            "language": language,
        }

    @classmethod
    async def get_players(cls, host, port):
        data = await cls.query(host, port, b"d")
        offset = 11
        count = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
        players = []
        for _ in range(count):
            if offset + 35 > len(data):
                break
            pid = data[offset]
            offset += 1
            name = data[offset:offset + 30].rstrip(b"\x00").decode("utf-8", errors="replace")
            offset += 30
            score = int.from_bytes(data[offset:offset + 4], "big")
            offset += 4
            ping = int.from_bytes(data[offset:offset + 4], "big")
            offset += 4
            players.append({"id": pid, "name": name, "score": score, "ping": ping})
        return players

    @classmethod
    async def get_rules(cls, host, port):
        data = await cls.query(host, port, b"r")
        offset = 11
        count = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
        rules = {}
        for _ in range(count):
            name, offset = _read_length_string(data, offset)
            value, offset = _read_length_string(data, offset)
            rules[name] = value
        return rules


class Samp(commands.Cog, name="samp"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()
        self.status_task = self.bot.loop.create_task(self.status_loop())

    def cog_unload(self):
        self.status_task.cancel()

    def get_guild_config(self, guild_id):
        gid = str(guild_id)
        if gid not in self.data:
            host = config.SAMP_SERVER_HOST
            if not host:
                return None
            self.data[gid] = {
                "host": host,
                "port": config.SAMP_SERVER_PORT,
                "status_channel": None,
                "status_enabled": False,
            }
            save_data(self.data)
        return self.data[gid]

    async def _setip(self, ctx, address):
        host, port = parse_address(address)
        if host is None:
            return await respond(ctx, content="Please provide a valid address like `play.server.com:7777`.")
        gid = str(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        cfg = self.data.setdefault(gid, {"host": host, "port": port, "status_channel": None, "status_enabled": False})
        cfg["host"] = host
        cfg["port"] = port
        save_data(self.data)
        embed = discord.Embed(title="SA-MP Server Set", color=discord.Color.green())
        embed.add_field(name="Address", value=f"{host}:{port}")
        await respond(ctx, embed=embed)

    @commands.command(name="sampsetip")
    async def sampsetip_prefix(self, ctx, *, address: str):
        await self._setip(ctx, address)

    @app_commands.command(name="sampsetip", description="Set your SA-MP server address (host:port)")
    async def sampsetip_slash(self, interaction: discord.Interaction, address: str):
        await self._setip(interaction, address)

    async def _status(self, ctx):
        cfg = self.get_guild_config(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if not cfg:
            return await respond(ctx, content="No SA-MP server configured. Use `!sampsetip <host:port>` or set `SAMP_SERVER_HOST` in `.env`.")
        start = time.monotonic()
        try:
            info = await SampServer.get_info(cfg["host"], cfg["port"])
        except ConnectionError as e:
            return await respond(ctx, content=f"**{cfg['host']}:{cfg['port']}** - {e}")
        latency = round((time.monotonic() - start) * 1000)
        color = discord.Color.green() if info["players"] > 0 else discord.Color.dark_gray()
        embed = discord.Embed(title=info["hostname"] or "SA-MP Server", color=color)
        embed.set_thumbnail(url="https://i.imgur.com/0bMqy9j.png")
        embed.add_field(name="Address", value=f"{info['host']}:{info['port']}")
        embed.add_field(name="Players", value=f"{info['players']} / {info['max_players']}", inline=True)
        status = "🔒 Password protected" if info["password"] else "✅ Open"
        embed.add_field(name="Status", value=status)
        embed.add_field(name="Gamemode", value=info["gamemode"] or "Unknown")
        embed.add_field(name="Language", value=info["language"] or "Unknown")
        embed.add_field(name="Ping", value=f"{latency}ms")
        embed.set_footer(text="SA-MP Server Monitor")
        await respond(ctx, embed=embed)

    @commands.command(name="sampstatus")
    async def sampstatus_prefix(self, ctx):
        await self._status(ctx)

    @app_commands.command(name="sampstatus", description="Show live SA-MP server info and player count")
    async def sampstatus_slash(self, interaction: discord.Interaction):
        await self._status(interaction)

    async def _players(self, ctx):
        cfg = self.get_guild_config(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if not cfg:
            return await respond(ctx, content="No SA-MP server configured. Use `!sampsetip <host:port>` or set `SAMP_SERVER_HOST` in `.env`.")
        try:
            info = await SampServer.get_info(cfg["host"], cfg["port"])
            players = await SampServer.get_players(cfg["host"], cfg["port"])
        except ConnectionError as e:
            return await respond(ctx, content=f"**{cfg['host']}:{cfg['port']}** - {e}")
        if not players:
            embed = discord.Embed(title=info["hostname"], description="No players online.", color=discord.Color.dark_gray())
            return await respond(ctx, embed=embed)
        embed = discord.Embed(
            title=f"Online Players ({len(players)}/{info['max_players']})",
            color=discord.Color.green(),
        )
        shown = 0
        field_lines = []
        for p in players:
            field_lines.append(f"`{p['id']:>2}` **{p['name']}** - Score: {p['score']} - Ping: {p['ping']}ms")
            shown += 1
            if len(field_lines) == 20:
                embed.add_field(name="Players", value="\n".join(field_lines), inline=False)
                field_lines = []
            if shown >= 60:
                break
        if field_lines:
            embed.add_field(name="Players", value="\n".join(field_lines), inline=False)
        if len(players) > shown:
            embed.set_footer(text=f"And {len(players) - shown} more...")
        await respond(ctx, embed=embed)

    @commands.command(name="sampplayers")
    async def sampplayers_prefix(self, ctx):
        await self._players(ctx)

    @app_commands.command(name="sampplayers", description="List players currently on the SA-MP server")
    async def sampplayers_slash(self, interaction: discord.Interaction):
        await self._players(interaction)

    async def _rules(self, ctx):
        cfg = self.get_guild_config(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if not cfg:
            return await respond(ctx, content="No SA-MP server configured. Use `!sampsetip <host:port>` or set `SAMP_SERVER_HOST` in `.env`.")
        try:
            info = await SampServer.get_info(cfg["host"], cfg["port"])
            rules = await SampServer.get_rules(cfg["host"], cfg["port"])
        except ConnectionError as e:
            return await respond(ctx, content=f"**{cfg['host']}:{cfg['port']}** - {e}")
        if not rules:
            return await respond(ctx, content="Server returned no rules.")
        embed = discord.Embed(title=f"Server Rules - {info['hostname']}", color=discord.Color.blue())
        lines = []
        for name, value in rules.items():
            lines.append(f"**{name}:** {value}")
            if len(lines) == 20:
                embed.add_field(name="Rules", value="\n".join(lines), inline=False)
                lines = []
        if lines:
            embed.add_field(name="Rules", value="\n".join(lines), inline=False)
        await respond(ctx, embed=embed)

    @commands.command(name="samprules")
    async def samprules_prefix(self, ctx):
        await self._rules(ctx)

    @app_commands.command(name="samprules", description="Show rules of the SA-MP server")
    async def samprules_slash(self, interaction: discord.Interaction):
        await self._rules(interaction)

    async def _setstatus(self, ctx, channel, enabled):
        cfg = self.get_guild_config(ctx.guild_id if isinstance(ctx, discord.Interaction) else ctx.guild.id)
        if not cfg:
            return await respond(ctx, content="No SA-MP server configured. Use `!sampsetip <host:port>` first.")
        cfg["status_channel"] = channel.id
        cfg["status_enabled"] = enabled
        save_data(self.data)
        state = "enabled" if enabled else "disabled"
        await respond(ctx, content=f"Auto status updates {state} in {channel.mention}. Updating every {UPDATE_INTERVAL}s.")

    @commands.command(name="sampsetstatus")
    @commands.has_permissions(administrator=True)
    async def sampsetstatus_prefix(self, ctx, channel: discord.TextChannel = None):
        if channel is None:
            return await ctx.send("Please specify a channel.")
        await self._setstatus(ctx, channel, True)

    @app_commands.command(name="sampsetstatus", description="Auto-update a channel with the player count")
    @app_commands.default_permissions(administrator=True)
    async def sampsetstatus_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await self._setstatus(interaction, channel, True)

    @commands.command(name="sampstopstatus")
    @commands.has_permissions(administrator=True)
    async def sampstopstatus_prefix(self, ctx):
        cfg = self.get_guild_config(ctx.guild.id)
        if cfg:
            cfg["status_enabled"] = False
            save_data(self.data)
        await ctx.send("Auto status updates stopped.")

    @app_commands.command(name="sampstopstatus", description="Stop auto player-count updates")
    @app_commands.default_permissions(administrator=True)
    async def sampstopstatus_slash(self, interaction: discord.Interaction):
        cfg = self.get_guild_config(interaction.guild.id)
        if cfg:
            cfg["status_enabled"] = False
            save_data(self.data)
        await interaction.response.send_message("Auto status updates stopped.", ephemeral=True)

    async def status_loop(self):
        await self.bot.wait_until_ready()
        while True:
            await asyncio.sleep(UPDATE_INTERVAL)
            for gid, cfg in list(self.data.items()):
                if not cfg.get("status_enabled") or not cfg.get("status_channel"):
                    continue
                guild = self.bot.get_guild(int(gid))
                if not guild:
                    continue
                channel = guild.get_channel(cfg["status_channel"])
                if not channel:
                    continue
                try:
                    info = await SampServer.get_info(cfg["host"], cfg["port"])
                    players = f"{info['players']}/{info['max_players']}"
                    if isinstance(channel, discord.VoiceChannel):
                        new_name = f"🎮 Players: {players}"
                        if len(new_name) > 100:
                            new_name = new_name[:100]
                        if channel.name != new_name:
                            await channel.edit(name=new_name)
                    else:
                        new_topic = f"🟢 Online: {players} | {info['hostname'][:80]}"
                        if channel.topic != new_topic:
                            await channel.edit(topic=new_topic)
                except Exception as e:
                    print(f"SAMP status update failed for guild {gid}: {e}")


async def setup(bot):
    await bot.add_cog(Samp(bot))
