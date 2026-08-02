import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import re

YT_DL_AVAILABLE = False
try:
    import yt_dlp
    YT_DL_AVAILABLE = True
except ImportError:
    pass

FFMPEG_AVAILABLE = False
try:
    import subprocess
    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    FFMPEG_AVAILABLE = True
except:
    pass


async def respond(ctx_or_interaction, embed=None, content=None, ephemeral=False):
    if isinstance(ctx_or_interaction, commands.Context):
        await ctx_or_interaction.send(embed=embed, content=content)
    else:
        if not ctx_or_interaction.response.is_done():
            await ctx_or_interaction.response.send_message(embed=embed, content=content, ephemeral=ephemeral)
        else:
            await ctx_or_interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral)


async def ensure_voice(ctx_or_interaction):
    if isinstance(ctx_or_interaction, commands.Context):
        author = ctx_or_interaction.author
    else:
        author = ctx_or_interaction.user
    if not author.voice or not author.voice.channel:
        await respond(ctx_or_interaction, content="You need to be in a voice channel first.")
        return None
    guild = ctx_or_interaction.guild
    if guild.voice_client:
        if guild.voice_client.channel != author.voice.channel:
            await guild.voice_client.move_to(author.voice.channel)
    else:
        await author.voice.channel.connect()
    return author.voice.channel


class MusicController:
    def __init__(self):
        self.queues = {}
        self.current = {}
        self.volume = {}
        self.loops = {}

    def get_queue(self, guild_id):
        gid = str(guild_id)
        if gid not in self.queues:
            self.queues[gid] = []
            self.current[gid] = None
            self.volume[gid] = 0.5
            self.loops[gid] = False
        return self.queues[gid]


controller = MusicController()

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "skip_download": True,
    "default_search": "ytsearch",
}


class Music(commands.Cog, name="music"):
    def __init__(self, bot):
        self.bot = bot

    async def _play(self, ctx, query):
        if not YT_DL_AVAILABLE or not FFMPEG_AVAILABLE:
            return await respond(ctx, content="Music requires yt-dlp and ffmpeg. Install with: pip install yt-dlp && install FFmpeg.")
        channel = await ensure_voice(ctx)
        if not channel:
            return
        guild_id = ctx.guild.id
        queue = controller.get_queue(guild_id)

        if not query:
            if queue:
                await respond(ctx, content="🎵 Resuming playback...")
            else:
                await respond(ctx, content="Please provide a song name or URL.")
            return

        await respond(ctx, content=f"🔍 Searching for `{query}`...")

        def search_sync(q):
            with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
                return ydl.extract_info(q, download=False)

        info = await asyncio.to_thread(search_sync, query)
        if not info:
            return await respond(ctx, content="Could not find that song.")

        if "entries" in info:
            entry = info["entries"][0]
        else:
            entry = info

        song = {
            "url": entry["url"],
            "title": entry.get("title", "Unknown"),
            "duration": entry.get("duration", 0),
            "webpage_url": entry.get("webpage_url", entry.get("url", "")),
            "thumbnail": entry.get("thumbnail", ""),
            "requester": ctx.author.id if isinstance(ctx, commands.Context) else ctx.user.id,
        }

        queue.append(song)

        if not ctx.guild.voice_client.is_playing() and not controller.current[str(guild_id)]:
            await self._play_next(ctx.guild)
        else:
            embed = discord.Embed(title="Added to Queue", description=f"[{song['title']}]({song['webpage_url']})", color=discord.Color.blue())
            minutes = song["duration"] // 60
            seconds = song["duration"] % 60
            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}")
            await respond(ctx, embed=embed)

    @commands.command(name="play")
    async def play_prefix(self, ctx, *, query=None):
        await self._play(ctx, query)

    @app_commands.command(name="play", description="Play a song or search on YouTube")
    async def play_slash(self, interaction: discord.Interaction, query: str):
        await self._play(interaction, query)

    # --- JOIN / LEAVE VOICE ---
    async def _join(self, ctx, channel):
        if channel is None:
            channel = await ensure_voice(ctx)
            if not channel:
                return
        guild = ctx.guild
        if guild.voice_client:
            if guild.voice_client.channel != channel:
                await guild.voice_client.move_to(channel)
                await respond(ctx, content=f"🔊 Moved to {channel.mention}.")
            else:
                await respond(ctx, content=f"Already in {channel.mention}.")
        else:
            await channel.connect()
            await respond(ctx, content=f"🔊 Joined {channel.mention}.")

    @commands.command(name="join")
    async def join_prefix(self, ctx, channel: discord.VoiceChannel = None):
        await self._join(ctx, channel)

    @app_commands.command(name="join", description="Make the bot join a voice channel")
    async def join_slash(self, interaction: discord.Interaction, channel: discord.VoiceChannel = None):
        await self._join(interaction, channel)

    async def _leave(self, ctx):
        guild = ctx.guild
        if guild.voice_client:
            await guild.voice_client.disconnect()
            await respond(ctx, content="👋 Left the voice channel.")
        else:
            await respond(ctx, content="I'm not in a voice channel.")

    @commands.command(name="leave")
    async def leave_prefix(self, ctx):
        await self._leave(ctx)

    @app_commands.command(name="leave", description="Disconnect the bot from voice")
    async def leave_slash(self, interaction: discord.Interaction):
        await self._leave(interaction)

    async def _play_next(self, guild):
        gid = str(guild.id)
        queue = controller.get_queue(gid)
        voice = guild.voice_client
        if not voice:
            return
        if not queue:
            controller.current[gid] = None
            return
        song = queue.pop(0)
        controller.current[gid] = song
        vol = controller.volume[gid]

        def after_play(err):
            if err:
                print(f"Playback error: {err}")
            coro = self._play_next(guild)
            fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
            try:
                fut.result()
            except:
                pass

        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(song["url"]), volume=vol)
        voice.play(source, after=after_play)

    async def _skip(self, ctx):
        channel = await ensure_voice(ctx)
        if not channel:
            return
        voice = ctx.guild.voice_client
        if voice and voice.is_playing():
            voice.stop()
            await respond(ctx, content="⏭️ Skipped!")
        else:
            await respond(ctx, content="Nothing is playing.")

    @commands.command(name="skip")
    async def skip_prefix(self, ctx):
        await self._skip(ctx)

    @app_commands.command(name="skip", description="Skip the current song")
    async def skip_slash(self, interaction: discord.Interaction):
        await self._skip(interaction)

    async def _stop(self, ctx):
        channel = await ensure_voice(ctx)
        if not channel:
            return
        gid = str(ctx.guild.id)
        controller.get_queue(gid).clear()
        controller.current[gid] = None
        voice = ctx.guild.voice_client
        if voice:
            if voice.is_playing():
                voice.stop()
            await voice.disconnect()
        await respond(ctx, content="⏹️ Stopped and disconnected.")

    @commands.command(name="stop")
    async def stop_prefix(self, ctx):
        await self._stop(ctx)

    @app_commands.command(name="stop", description="Stop music and clear queue")
    async def stop_slash(self, interaction: discord.Interaction):
        await self._stop(interaction)

    async def _queue(self, ctx):
        queue = controller.get_queue(ctx.guild.id)
        if not queue:
            return await respond(ctx, content="Queue is empty.")
        embed = discord.Embed(title="Music Queue", color=discord.Color.blue())
        for i, song in enumerate(queue[:10], 1):
            minutes = song["duration"] // 60
            seconds = song["duration"] % 60
            embed.add_field(name=f"{i}. {song['title']}", value=f"{minutes}:{seconds:02d}", inline=False)
        if len(queue) > 10:
            embed.set_footer(text=f"+ {len(queue) - 10} more songs")
        await respond(ctx, embed=embed)

    @commands.command(name="queue")
    async def queue_prefix(self, ctx):
        await self._queue(ctx)

    @app_commands.command(name="queue", description="View the music queue")
    async def queue_slash(self, interaction: discord.Interaction):
        await self._queue(interaction)

    async def _nowplaying(self, ctx):
        gid = str(ctx.guild.id)
        song = controller.current.get(gid)
        if not song:
            return await respond(ctx, content="Nothing is playing.")
        embed = discord.Embed(title="Now Playing", description=f"[{song['title']}]({song['webpage_url']})", color=discord.Color.blue())
        if song.get("thumbnail"):
            embed.set_thumbnail(url=song["thumbnail"])
        minutes = song["duration"] // 60
        seconds = song["duration"] % 60
        embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}")
        await respond(ctx, embed=embed)

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying_prefix(self, ctx):
        await self._nowplaying(ctx)

    @app_commands.command(name="nowplaying", description="Show what's currently playing")
    async def nowplaying_slash(self, interaction: discord.Interaction):
        await self._nowplaying(interaction)

    async def _volume(self, ctx, vol):
        if vol is None:
            current_vol = controller.volume.get(str(ctx.guild.id), 0.5)
            return await respond(ctx, content=f"Current volume: {int(current_vol * 100)}%")
        if vol < 0 or vol > 200:
            return await respond(ctx, content="Volume must be between 0 and 200.")
        controller.volume[str(ctx.guild.id)] = vol / 100
        voice = ctx.guild.voice_client
        if voice and voice.source:
            voice.source.volume = vol / 100
        await respond(ctx, content=f"Volume set to {vol}%")

    @commands.command(name="volume")
    async def volume_prefix(self, ctx, vol: int = None):
        await self._volume(ctx, vol)

    @app_commands.command(name="volume", description="Set or view volume")
    async def volume_slash(self, interaction: discord.Interaction, vol: app_commands.Range[int, 0, 200] = None):
        await self._volume(interaction, vol)

    async def _pause(self, ctx):
        voice = ctx.guild.voice_client
        if voice and voice.is_playing():
            voice.pause()
            await respond(ctx, content="⏸️ Paused.")
        else:
            await respond(ctx, content="Nothing is playing.")

    @commands.command(name="pause")
    async def pause_prefix(self, ctx):
        await self._pause(ctx)

    @app_commands.command(name="pause", description="Pause playback")
    async def pause_slash(self, interaction: discord.Interaction):
        await self._pause(interaction)

    async def _resume(self, ctx):
        voice = ctx.guild.voice_client
        if voice and voice.is_paused():
            voice.resume()
            await respond(ctx, content="▶️ Resumed.")
        elif voice and voice.is_playing():
            await respond(ctx, content="Already playing.")
        else:
            await respond(ctx, content="Nothing to resume.")

    @commands.command(name="resume")
    async def resume_prefix(self, ctx):
        await self._resume(ctx)

    @app_commands.command(name="resume", description="Resume playback")
    async def resume_slash(self, interaction: discord.Interaction):
        await self._resume(interaction)


async def setup(bot):
    await bot.add_cog(Music(bot))
