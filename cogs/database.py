import asyncio

import pymysql
import discord
from discord import app_commands
from discord.ext import commands

import config
from cogs.utility import respond

ADMIN_LEVELS = {1: "A1", 2: "A2", 3: "A3", 4: "A4", 5: "A5", 6: "A6", 7: "A7", 8: "A8"}


def _connect():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=6,
        cursorclass=pymysql.cursors.DictCursor,
    )


async def fetchall(query, params=None):
    loop = asyncio.get_running_loop()

    def _run():
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()
        finally:
            conn.close()

    return await loop.run_in_executor(None, _run)


async def fetchone(query, params=None):
    rows = await fetchall(query, params)
    return rows[0] if rows else None


def _fmt_money(value):
    try:
        return f"${int(value):,}"
    except (TypeError, ValueError):
        return "$0"


def _fmt_playtime(hours, minutes):
    hours = hours or 0
    minutes = minutes or 0
    if hours >= 24:
        days, rem = divmod(hours, 24)
        return f"{days}d {rem}h {minutes}m"
    return f"{hours}h {minutes}m"


def _clean(value):
    if value is None:
        return None
    return str(value).strip() or None


def _admin_label(level):
    return ADMIN_LEVELS.get(level, f"A{level}") if level else None


USER_SELECT = (
    "SELECT uid, username, regdate, lastlogin, gender, cash, bank, level, exp, "
    "hours, minutes, adminlevel, helperlevel, faction, factionrank, gang, gangrank, "
    "vippackage, warnings, marriedto, carlicense, gunlicense, phone, paycheck "
    "FROM users WHERE {cond} AND setup = 0 ORDER BY uid LIMIT 1"
)


def _faction_name(row):
    name = _clean(row.get("name")) or _clean(row.get("shortname"))
    return name or f"Faction {row.get('id')}"


class Database(commands.Cog, name="db"):
    def __init__(self, bot):
        self.bot = bot

    async def _stats(self, ctx, name):
        query = USER_SELECT.format(cond="username = %s")
        row = await fetchone(query, (name,))
        if not row:
            row = await fetchone(USER_SELECT.format(cond="username LIKE %s"), (f"%{name}%",))
        if not row:
            return await respond(ctx, content=f"No player named `{name}` found in the database.")
        uid = row["uid"]
        counts = await asyncio.gather(
            fetchone("SELECT COUNT(*) AS c FROM kills WHERE killer_uid = %s", (uid,)),
            fetchone("SELECT COUNT(*) AS c FROM kills WHERE target_uid = %s", (uid,)),
            fetchone("SELECT COUNT(*) AS c FROM vehicles WHERE ownerid = %s", (uid,)),
            fetchone("SELECT COUNT(*) AS c FROM houses WHERE ownerid = %s", (uid,)),
            fetchone("SELECT COUNT(*) AS c FROM businesses WHERE ownerid = %s", (uid,)),
        )
        kills = counts[0]["c"] if counts[0] else 0
        deaths = counts[1]["c"] if counts[1] else 0
        vehicles = counts[2]["c"] if counts[2] else 0
        houses = counts[3]["c"] if counts[3] else 0
        businesses = counts[4]["c"] if counts[4] else 0

        faction = "None"
        if row["faction"] and row["faction"] > 0:
            fr = await fetchone("SELECT name, shortname FROM factions WHERE id = %s", (row["faction"],))
            fname = _faction_name(fr) if fr else f"Faction {row['faction']}"
            rank = None
            rr = await fetchone(
                "SELECT name FROM factionranks WHERE id = %s AND rank = %s",
                (row["faction"], row["factionrank"]),
            )
            if rr:
                rank = _clean(rr["name"])
            faction = f"{fname}" + (f" - {rank}" if rank else "")

        gang = "None"
        if row["gang"] and row["gang"] > 0:
            gr = await fetchone("SELECT name FROM gangs WHERE id = %s", (row["gang"],))
            gname = _clean(gr["name"]) if gr else f"Gang {row['gang']}"
            rank = None
            rr = await fetchone(
                "SELECT name FROM gangranks WHERE id = %s AND rank = %s",
                (row["gang"], row["gangrank"]),
            )
            if rr:
                rank = _clean(rr["name"])
            gang = f"{gname}" + (f" - {rank}" if rank else "")

        admin = "Player"
        if row["adminlevel"] and row["adminlevel"] > 0:
            admin = _admin_label(row["adminlevel"])
        if row["helperlevel"] and row["helperlevel"] > 0:
            admin += f" (+Helper {row['helperlevel']})"

        vip = "None"
        if row["vippackage"]:
            vip = f"Package {row['vippackage']}"

        cash = _fmt_money(row["cash"])
        bank = _fmt_money(row["bank"])
        try:
            total = _fmt_money((row["cash"] or 0) + (row["bank"] or 0))
        except (TypeError, ValueError):
            total = cash

        embed = discord.Embed(
            title=f"Player Stats - {row['username']}",
            color=discord.Color.green() if row["adminlevel"] else discord.Color.blue(),
        )
        embed.add_field(name="Level", value=f"{row['level']} (XP: {row['exp']})", inline=True)
        embed.add_field(name="Money", value=f"Cash: {cash}\nBank: {bank}\nTotal: {total}", inline=True)
        embed.add_field(name="Playtime", value=_fmt_playtime(row["hours"], row["minutes"]), inline=True)
        embed.add_field(name="Registered", value=str(row["regdate"] or "Unknown"), inline=True)
        embed.add_field(name="Last Login", value=str(row["lastlogin"] or "Unknown"), inline=True)
        embed.add_field(name="Admin", value=admin, inline=True)
        embed.add_field(name="Faction", value=faction, inline=True)
        embed.add_field(name="Gang", value=gang, inline=True)
        embed.add_field(name="VIP", value=vip, inline=True)
        embed.add_field(name="K / D", value=f"{kills} / {deaths}", inline=True)
        embed.add_field(name="Property", value=f"Vehicles: {vehicles}\nHouses: {houses}\nBusinesses: {businesses}", inline=True)
        licenses = []
        licenses.append("Car" if row["carlicense"] else "No car")
        licenses.append("Gun" if row["gunlicense"] else "No gun")
        embed.add_field(name="Licenses", value=", ".join(licenses), inline=True)
        embed.add_field(name="Warnings", value=str(row["warnings"]), inline=True)
        embed.set_footer(text=f"UID: {uid}")
        await respond(ctx, embed=embed)

    @commands.command(name="stats")
    async def stats_prefix(self, ctx, *, name: str):
        await self._stats(ctx, name)

    @app_commands.command(name="stats", description="View a player's in-game stats")
    async def stats_slash(self, interaction: discord.Interaction, name: str):
        await self._stats(interaction, name)

    async def _top(self, ctx, by):
        by = (by or "level").lower()
        if by not in ("level", "cash"):
            by = "level"
        column = "cash" if by == "cash" else "level"
        rows = await fetchall(
            f"SELECT username, level, cash, bank FROM users WHERE setup = 0 "
            f"ORDER BY {column} DESC LIMIT 10"
        )
        if not rows:
            return await respond(ctx, content="No players found in the database.")
        title = "Top 10 Players - Cash" if by == "cash" else "Top 10 Players - Level"
        embed = discord.Embed(title=title, color=discord.Color.gold())
        lines = []
        for i, r in enumerate(rows, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"`{i:>2}`")
            if by == "cash":
                value = f"{medal} **{r['username']}** - {_fmt_money(r['cash'])}"
            else:
                value = f"{medal} **{r['username']}** - Level {r['level']} (XP: {r['exp']})"
            lines.append(value)
            if len(lines) == 10:
                embed.add_field(name="Rankings", value="\n".join(lines), inline=False)
                lines = []
        if lines:
            embed.add_field(name="Rankings", value="\n".join(lines), inline=False)
        await respond(ctx, embed=embed)

    @commands.command(name="top")
    async def top_prefix(self, ctx, by: str = "level"):
        await self._top(ctx, by)

    @app_commands.command(name="top", description="Top players by level or cash")
    @app_commands.choices(by=[
        app_commands.Choice(name="Level", value="level"),
        app_commands.Choice(name="Cash", value="cash"),
    ])
    async def top_slash(
        self,
        interaction: discord.Interaction,
        by: app_commands.Choice[str] = None,
    ):
        await self._top(interaction, by.value if by else "level")

    async def _admins(self, ctx):
        rows = await fetchall(
            "SELECT username, adminlevel, helperlevel, lastlogin FROM users "
            "WHERE setup = 0 AND (adminlevel > 0 OR helperlevel > 0) "
            "ORDER BY adminlevel DESC, helperlevel DESC LIMIT 30"
        )
        if not rows:
            return await respond(ctx, content="No admins found in the database.")
        embed = discord.Embed(title=f"Staff List ({len(rows)})", color=discord.Color.green())
        admins = [r for r in rows if r["adminlevel"] > 0]
        helpers = [r for r in rows if r["adminlevel"] == 0 and r["helperlevel"] > 0]
        lines = []
        for r in admins:
            lines.append(f"**{_admin_label(r['adminlevel'])}** {r['username']} - {str(r['lastlogin'] or 'Never')}")
        if lines:
            for i in range(0, len(lines), 15):
                embed.add_field(name="Admins", value="\n".join(lines[i:i + 15]), inline=False)
        hlines = []
        for r in helpers:
            hlines.append(f"**Helper {r['helperlevel']}** {r['username']} - {str(r['lastlogin'] or 'Never')}")
        if hlines:
            embed.add_field(name="Helpers", value="\n".join(hlines), inline=False)
        await respond(ctx, embed=embed)

    @commands.command(name="admins")
    async def admins_prefix(self, ctx):
        await self._admins(ctx)

    @app_commands.command(name="admins", description="List admins and helpers")
    async def admins_slash(self, interaction: discord.Interaction):
        await self._admins(interaction)

    async def _faction(self, ctx, name):
        if not name:
            rows = await fetchall(
                "SELECT f.id, f.name, f.leader, f.shortname, COUNT(u.uid) AS members "
                "FROM factions f LEFT JOIN users u ON u.faction = f.id AND u.setup = 0 "
                "GROUP BY f.id, f.name, f.leader, f.shortname ORDER BY f.id"
            )
            if not rows:
                return await respond(ctx, content="No factions found in the database.")
            embed = discord.Embed(title="Factions", color=discord.Color.blue())
            lines = []
            for r in rows:
                lines.append(
                    f"**{_faction_name(r)}** - Leader: {_clean(r['leader']) or 'None'} - Members: {r['members']}"
                )
            for i in range(0, len(lines), 10):
                embed.add_field(name="Factions", value="\n".join(lines[i:i + 10]), inline=False)
            return await respond(ctx, embed=embed)
        fr = await fetchone(
            "SELECT id, name, leader, shortname FROM factions WHERE name LIKE %s OR shortname LIKE %s LIMIT 1",
            (f"%{name}%", f"%{name}%"),
        )
        if not fr:
            return await respond(ctx, content=f"No faction found matching `{name}`.")
        members = await fetchall(
            "SELECT u.username, u.factionrank, fr.name AS rank_name FROM users u "
            "LEFT JOIN factionranks fr ON fr.id = u.faction AND fr.rank = u.factionrank "
            "WHERE u.faction = %s AND u.setup = 0 ORDER BY u.factionrank DESC, u.username",
            (fr["id"],),
        )
        embed = discord.Embed(
            title=_faction_name(fr),
            description=f"Leader: {_clean(fr['leader']) or 'None'}\nMembers: {len(members)}",
            color=discord.Color.blue(),
        )
        if members:
            lines = []
            for m in members:
                rank = _clean(m["rank_name"]) or f"Rank {m['factionrank']}"
                lines.append(f"**{rank}** - {m['username']}")
            for i in range(0, len(lines), 20):
                embed.add_field(name="Members", value="\n".join(lines[i:i + 20]), inline=False)
        else:
            embed.add_field(name="Members", value="No members.")
        await respond(ctx, embed=embed)

    @commands.command(name="faction")
    async def faction_prefix(self, ctx, *, name: str = None):
        await self._faction(ctx, name)

    @app_commands.command(name="faction", description="List factions or view a faction's members")
    async def faction_slash(self, interaction: discord.Interaction, name: str = None):
        await self._faction(interaction, name)

    async def _gang(self, ctx, name):
        if not name:
            rows = await fetchall(
                "SELECT g.id, g.name, g.leader, g.motd, COUNT(u.uid) AS members "
                "FROM gangs g LEFT JOIN users u ON u.gang = g.id AND u.setup = 0 "
                "GROUP BY g.id, g.name, g.leader, g.motd ORDER BY g.id"
            )
            if not rows:
                return await respond(ctx, content="No gangs found in the database.")
            embed = discord.Embed(title="Gangs", color=discord.Color.purple())
            lines = []
            for r in rows:
                lines.append(
                    f"**{_clean(r['name']) or r['id']}** - Leader: {_clean(r['leader']) or 'None'} - Members: {r['members']}"
                )
            for i in range(0, len(lines), 10):
                embed.add_field(name="Gangs", value="\n".join(lines[i:i + 10]), inline=False)
            return await respond(ctx, embed=embed)
        gr = await fetchone(
            "SELECT id, name, leader, motd FROM gangs WHERE name LIKE %s LIMIT 1", (f"%{name}%",)
        )
        if not gr:
            return await respond(ctx, content=f"No gang found matching `{name}`.")
        members = await fetchall(
            "SELECT u.username, u.gangrank, gr.name AS rank_name FROM users u "
            "LEFT JOIN gangranks gr ON gr.id = u.gang AND gr.rank = u.gangrank "
            "WHERE u.gang = %s AND u.setup = 0 ORDER BY u.gangrank DESC, u.username",
            (gr["id"],),
        )
        embed = discord.Embed(
            title=_clean(gr["name"]) or f"Gang {gr['id']}",
            description=f"Leader: {_clean(gr['leader']) or 'None'}\nMembers: {len(members)}",
            color=discord.Color.purple(),
        )
        if members:
            lines = []
            for m in members:
                rank = _clean(m["rank_name"]) or f"Rank {m['gangrank']}"
                lines.append(f"**{rank}** - {m['username']}")
            for i in range(0, len(lines), 20):
                embed.add_field(name="Members", value="\n".join(lines[i:i + 20]), inline=False)
        else:
            embed.add_field(name="Members", value="No members.")
        await respond(ctx, embed=embed)

    @commands.command(name="gang")
    async def gang_prefix(self, ctx, *, name: str = None):
        await self._gang(ctx, name)

    @app_commands.command(name="gang", description="List gangs or view a gang's members")
    async def gang_slash(self, interaction: discord.Interaction, name: str = None):
        await self._gang(interaction, name)


async def setup(bot):
    await bot.add_cog(Database(bot))
