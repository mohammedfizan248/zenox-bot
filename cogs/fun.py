import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import random

DATA_FILE = "data/economy.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


SLOTS_PAYOUT = {"🍎": 3, "🍒": 5, "🍀": 10, "⭐": 20, "💎": 50}


async def respond(ctx_or_interaction, embed=None, content=None):
    if isinstance(ctx_or_interaction, commands.Context):
        await ctx_or_interaction.send(embed=embed, content=content)
    else:
        if not ctx_or_interaction.response.is_done():
            await ctx_or_interaction.response.send_message(embed=embed, content=content)
        else:
            await ctx_or_interaction.followup.send(embed=embed, content=content)


class Fun(commands.Cog, name="fun"):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

    def get_user(self, uid):
        uid = str(uid)
        if uid not in self.data:
            self.data[uid] = {"balance": 100, "daily": 0}
        return uid

    async def _balance(self, ctx, member):
        member = member or (ctx.author if isinstance(ctx, commands.Context) else ctx.user)
        uid = self.get_user(member.id)
        await respond(ctx, content=f"{member.mention} has **${self.data[uid]['balance']}**")

    @commands.command(name="balance")
    async def balance_prefix(self, ctx, member: discord.Member = None):
        await self._balance(ctx, member)

    @app_commands.command(name="balance", description="Check your balance")
    async def balance_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        await self._balance(interaction, member)

    async def _daily(self, ctx):
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        uid = self.get_user(author.id)
        now = discord.utils.utcnow().timestamp()
        if self.data[uid]["daily"] and now - self.data[uid]["daily"] < 86400:
            remaining = 86400 - (now - self.data[uid]["daily"])
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            return await respond(ctx, content=f"You already claimed your daily! Come back in {hours}h {mins}m.")
        reward = random.randint(50, 200)
        self.data[uid]["balance"] += reward
        self.data[uid]["daily"] = now
        save_data(self.data)
        await respond(ctx, content=f"{author.mention} claimed **${reward}** daily bonus!")

    @commands.command(name="daily")
    async def daily_prefix(self, ctx):
        await self._daily(ctx)

    @app_commands.command(name="daily", description="Claim your daily bonus")
    async def daily_slash(self, interaction: discord.Interaction):
        await self._daily(interaction)

    async def _give(self, ctx, member, amount):
        if member is None:
            return await respond(ctx, content="Please specify a member.")
        if amount <= 0:
            return await respond(ctx, content="Amount must be positive.")
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        if member == author:
            return await respond(ctx, content="You can't give money to yourself.")
        sender_uid = self.get_user(author.id)
        if self.data[sender_uid]["balance"] < amount:
            return await respond(ctx, content="Insufficient funds!")
        recv_uid = self.get_user(member.id)
        self.data[sender_uid]["balance"] -= amount
        self.data[recv_uid]["balance"] += amount
        save_data(self.data)
        await respond(ctx, content=f"{author.mention} gave **${amount}** to {member.mention}!")

    @commands.command(name="give")
    async def give_prefix(self, ctx, member: discord.Member = None, amount: int = None):
        await self._give(ctx, member, amount)

    @app_commands.command(name="give", description="Give money to another member")
    async def give_slash(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await self._give(interaction, member, amount)

    async def _slots(self, ctx, bet):
        if bet is None or bet <= 0:
            return await respond(ctx, content="Please specify a valid bet amount.")
        author = ctx.author if isinstance(ctx, commands.Context) else ctx.user
        uid = self.get_user(author.id)
        if self.data[uid]["balance"] < bet:
            return await respond(ctx, content="Insufficient funds!")
        slots = ["🍎", "🍒", "🍀", "⭐", "💎", "🍎", "🍒", "🍀"]
        r1 = random.choice(slots)
        r2 = random.choice(slots)
        r3 = random.choice(slots)
        result = f"**{r1} | {r2} | {r3}**"
        if r1 == r2 == r3:
            payout = SLOTS_PAYOUT.get(r1, 3) * bet
            self.data[uid]["balance"] += payout - bet
            msg = f"JACKPOT! You won **${payout}**!"
        elif r1 == r2 or r2 == r3:
            payout = bet // 2
            self.data[uid]["balance"] -= payout
            msg = f"Small win! You got **${payout}**!"
        else:
            self.data[uid]["balance"] -= bet
            msg = "You lost!"
        save_data(self.data)
        embed = discord.Embed(title="🎰 Slots", description=f"{result}\n\n{msg}", color=discord.Color.blue())
        await respond(ctx, embed=embed)

    @commands.command(name="slots")
    async def slots_prefix(self, ctx, bet: int = None):
        await self._slots(ctx, bet)

    @app_commands.command(name="slots", description="Play slots")
    async def slots_slash(self, interaction: discord.Interaction, bet: int):
        await self._slots(interaction, bet)

    # --- 8BALL ---
    RESPONSES = ["Yes", "No", "Maybe", "Ask again later", "Definitely not", "Absolutely", "I don't think so", "Signs point to yes", "Better not tell you now", "Outlook good"]

    @commands.command(name="8ball")
    async def ball_prefix(self, ctx, *, question=None):
        if not question:
            return await ctx.send("Ask me a question!")
        await ctx.send(f"🎱 {random.choice(self.RESPONSES)}")

    @app_commands.command(name="8ball", description="Ask the magic 8ball a question")
    async def ball_slash(self, interaction: discord.Interaction, question: str):
        await interaction.response.send_message(f"🎱 {random.choice(self.RESPONSES)}")

    # --- MEME ---
    MEME_FACTS = [
        "Did you know? Discord was released in 2015!",
        "Fun fact: Python was named after Monty Python.",
        "Did you know? The first computer bug was a real moth.",
        "Fun fact: The Eiffel Tower grows 6 inches in summer.",
        "Did you know? Octopuses have three hearts!",
    ]

    @commands.command(name="meme")
    async def meme_prefix(self, ctx):
        await ctx.send(f"📢 {random.choice(self.MEME_FACTS)}")

    @app_commands.command(name="meme", description="Get a random fun fact")
    async def meme_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"📢 {random.choice(self.MEME_FACTS)}")


async def setup(bot):
    await bot.add_cog(Fun(bot))
