import asyncio
import functools
import subprocess

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

import config
from utils.helpers import embed, error_embed, success_embed

# ─── IMPORTANT ───────────────────────────────────────────────────────────────
# FFmpeg trebuie instalat separat: https://ffmpeg.org/download.html
# Adaugă FFmpeg în PATH sau setează FFMPEG_PATH mai jos.
FFMPEG_PATH = "ffmpeg"
# ─────────────────────────────────────────────────────────────────────────────

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "nocheckcertificate": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
    "extract_flat": False,
    "ignoreerrors": False,
    "socket_timeout": 30,
    "retries": 3,
    "fragment_retries": 3,
    # Mai puține blocaje / schimbări de client de la YouTube
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}

# -nostdin evită ca FFmpeg să aștepte input pe Windows (înghețe / reluări ciudate)
FFMPEG_OPTIONS = {
    "executable": FFMPEG_PATH,
    "before_options": (
        "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    ),
    "options": "-vn -ar 48000 -ac 2",
    "stderr": subprocess.DEVNULL,
}


class Song:
    def __init__(self, data: dict):
        self.title = data.get("title", "Unknown")
        self.url = data.get("url") or ""
        if not self.url and data.get("requested_formats"):
            self.url = data["requested_formats"][0].get("url", "")
        if not self.url and data.get("formats"):
            for f in data["formats"]:
                if f.get("url") and f.get("vcodec") == "none":
                    self.url = f["url"]
                    break
        self.webpage_url = data.get("webpage_url", data.get("url", ""))
        self.duration = data.get("duration", 0)
        self.thumbnail = data.get("thumbnail", "")
        self.uploader = data.get("uploader", "Unknown")
        self.requester = None

    def duration_str(self) -> str:
        if not self.duration:
            return "LIVE"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class MusicPlayer:
    def __init__(self, ctx_or_inter):
        self.guild = ctx_or_inter.guild
        self.channel = ctx_or_inter.channel
        self.queue: list[Song] = []
        self.current: Song | None = None
        self.volume = 0.5
        self.loop = False

    @property
    def vc(self) -> discord.VoiceClient | None:
        return self.guild.voice_client


async def fetch_song(query: str, loop: asyncio.AbstractEventLoop) -> Song | None:
    ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
    try:
        partial = functools.partial(ytdl.extract_info, query, download=False)
        data = await loop.run_in_executor(None, partial)
        if not data:
            return None
        if "entries" in data:
            ent = data["entries"]
            if not ent:
                return None
            data = ent[0]
            if data is None:
                return None
        return Song(data)
    except Exception as e:
        print(f"[Music] yt-dlp: {e}")
        return None


class Music(commands.Cog, name="Muzică"):
    """Sistem de muzică pentru canale vocale."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}
        # Un singur task de auto-disconnect per guild (evită zeci de sleep(30) suprapuse)
        self._alone_disconnect_tasks: dict[int, asyncio.Task] = {}
        self._play_locks: dict[int, asyncio.Lock] = {}

    def cog_unload(self):
        for t in list(self._alone_disconnect_tasks.values()):
            if t and not t.done():
                t.cancel()
        self._alone_disconnect_tasks.clear()

    def _play_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._play_locks:
            self._play_locks[guild_id] = asyncio.Lock()
        return self._play_locks[guild_id]

    def get_player(self, interaction: discord.Interaction) -> MusicPlayer:
        if interaction.guild.id not in self.players:
            self.players[interaction.guild.id] = MusicPlayer(interaction)
        return self.players[interaction.guild.id]

    def destroy_player(self, guild_id: int):
        self.players.pop(guild_id, None)
        self._cancel_alone_disconnect(guild_id)

    def _cancel_alone_disconnect(self, guild_id: int):
        t = self._alone_disconnect_tasks.pop(guild_id, None)
        if t and not t.done():
            t.cancel()

    def _schedule_alone_disconnect(self, guild: discord.Guild):
        """Dacă în canalul muzicii nu e niciun om, deconectează după 90s (un singur timer)."""
        vc = guild.voice_client
        if not vc or not vc.channel:
            return

        humans = [m for m in vc.channel.members if not m.bot]
        if humans:
            self._cancel_alone_disconnect(guild.id)
            return

        self._cancel_alone_disconnect(guild.id)

        async def _job():
            try:
                await asyncio.sleep(90)
                vc2 = guild.voice_client
                if not vc2 or not vc2.channel or not vc2.is_connected():
                    return
                if [m for m in vc2.channel.members if not m.bot]:
                    return
                self.destroy_player(guild.id)
                await vc2.disconnect(force=True)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[Music] auto-disconnect: {e}")

        self._alone_disconnect_tasks[guild.id] = asyncio.create_task(_job())

    async def _ensure_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            return None
        ch = interaction.user.voice.channel
        vc = interaction.guild.voice_client
        try:
            if vc is None:
                return await ch.connect(timeout=60.0, reconnect=True, self_deaf=False)
            if vc.channel != ch:
                await vc.move_to(ch)
            return interaction.guild.voice_client
        except Exception as e:
            print(f"[Music] voice connect/move: {e}")
            return None

    def _schedule_after_track(self, guild: discord.Guild):
        def _after(err):
            if err:
                print(f"[Music] track end error: {err}")
            try:
                asyncio.run_coroutine_threadsafe(self._play_next(guild), self.bot.loop)
            except RuntimeError:
                pass

        return _after

    async def _play_next(self, guild: discord.Guild):
        lock = self._play_lock(guild.id)
        async with lock:
            await asyncio.sleep(0.2)

            player = self.players.get(guild.id)
            if not player:
                return

            vc = guild.voice_client
            if not vc or not vc.is_connected():
                return

            if vc.is_playing() or vc.is_paused():
                return

            song: Song | None = None
            for _ in range(55):
                if player.loop and player.current:
                    song = player.current
                elif player.queue:
                    song = player.queue.pop(0)
                    player.current = song
                else:
                    player.current = None
                    return

                if song.url and song.url.startswith(("http://", "https://")):
                    break
                song = None
            else:
                player.current = None
                return

            try:
                raw = discord.FFmpegPCMAudio(song.url, **FFMPEG_OPTIONS)
                source = discord.PCMVolumeTransformer(raw, volume=player.volume)
            except Exception as err:
                print(f"[Music] FFmpegPCMAudio: {err}")
                asyncio.run_coroutine_threadsafe(self._play_next(guild), self.bot.loop)
                return

            try:
                vc.play(source, after=self._schedule_after_track(guild))
            except discord.ClientException as err:
                print(f"[Music] vc.play: {err}")
                await asyncio.sleep(0.4)
                asyncio.run_coroutine_threadsafe(self._play_next(guild), self.bot.loop)
                return

        e = embed(
            title="🎵 Redare acum",
            description=f"**[{song.title}]({song.webpage_url})**",
            color=config.COLOR_PRIMARY,
            thumbnail=song.thumbnail,
            fields=[("⏱️ Durată", song.duration_str(), True)],
        )
        try:
            await player.channel.send(embed=e)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        vc = member.guild.voice_client
        if not vc or not vc.channel:
            return

        our = vc.channel

        # Cineva a intrat în canalul botului → anulăm deconectarea programată
        if after.channel == our and not member.bot:
            self._cancel_alone_disconnect(member.guild.id)
            return

        # Cineva a ieșit din canalul botului (sau s-a mutat în altul)
        if before.channel == our and after.channel != our:
            self._schedule_alone_disconnect(member.guild)

    @app_commands.command(name="join", description="Botul intră în canalul tău vocal")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message(
                embed=error_embed("Trebuie să fii într-un canal vocal!"), ephemeral=True
            )
        vc = await self._ensure_voice(interaction)
        if not vc:
            return await interaction.response.send_message(
                embed=error_embed("Nu mă pot conecta la voice. Verifică permisiunile botului."),
                ephemeral=True,
            )
        await interaction.response.send_message(
            embed=success_embed(f"Conectat în **{interaction.user.voice.channel.name}**! 🎵")
        )

    @app_commands.command(name="leave", description="Botul iese din canalul vocal")
    async def leave(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(
                embed=error_embed("Botul nu este în niciun canal vocal."), ephemeral=True
            )
        self.destroy_player(interaction.guild.id)
        await vc.disconnect(force=True)
        await interaction.response.send_message(embed=success_embed("Deconectat! 👋"))

    @app_commands.command(name="play", description="Redă o melodie (URL YouTube sau termen de căutare)")
    @app_commands.describe(query="Link YouTube sau numele melodiei")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            return await interaction.response.send_message(
                embed=error_embed("Trebuie să fii într-un canal vocal!"), ephemeral=True
            )

        await interaction.response.defer()

        vc = await self._ensure_voice(interaction)
        if not vc:
            return await interaction.followup.send(
                embed=error_embed(
                    "Nu mă pot conecta la voice (Connect + Speak pentru rolul botului)."
                )
            )

        player = self.get_player(interaction)
        song = await fetch_song(query, self.bot.loop)
        if not song:
            return await interaction.followup.send(
                embed=error_embed("Nu am putut găsi melodia. Încearcă alt link sau alt termen.")
            )
        if not song.url or not song.url.startswith(("http://", "https://")):
            return await interaction.followup.send(
                embed=error_embed("Nu am obținut un URL de redare valid. Încearcă altă sursă.")
            )
        song.requester = interaction.user

        if vc.is_playing() or vc.is_paused():
            player.queue.append(song)
            e = embed(
                title="➕ Adăugat în coadă",
                description=f"**[{song.title}]({song.webpage_url})**",
                color=config.COLOR_PRIMARY,
                thumbnail=song.thumbnail,
                fields=[
                    ("⏱️ Durată", song.duration_str(), True),
                    ("👤 Uploader", song.uploader, True),
                    ("📋 Poziție în coadă", str(len(player.queue)), True),
                ],
            )
            return await interaction.followup.send(embed=e)

        player.current = song

        async with self._play_lock(interaction.guild.id):
            try:
                raw = discord.FFmpegPCMAudio(song.url, **FFMPEG_OPTIONS)
                source = discord.PCMVolumeTransformer(raw, volume=player.volume)
            except Exception as err:
                player.current = None
                return await interaction.followup.send(
                    embed=error_embed(
                        "Nu am putut porni FFmpeg. Verifică instalarea **FFmpeg** în PATH.\n"
                        f"_({err})_"
                    )
                )

            try:
                vc.play(source, after=self._schedule_after_track(interaction.guild))
            except discord.ClientException as err:
                player.current = None
                return await interaction.followup.send(
                    embed=error_embed(f"Nu pot reda acum: {err}")
                )

        e = embed(
            title="🎵 Redare acum",
            description=f"**[{song.title}]({song.webpage_url})**",
            color=config.COLOR_PRIMARY,
            thumbnail=song.thumbnail,
            fields=[
                ("⏱️ Durată", song.duration_str(), True),
                ("👤 Uploader", song.uploader, True),
                ("👤 Cerut de", song.requester.display_name, True),
            ],
        )
        await interaction.followup.send(embed=e)

    @app_commands.command(name="skip", description="Treci la melodia următoare")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            return await interaction.response.send_message(
                embed=error_embed("Nu se redă nimic."), ephemeral=True
            )
        vc.stop()
        await interaction.response.send_message(embed=success_embed("⏭️ Melodie trecută!"))

    @app_commands.command(name="pause", description="Pauză la melodia curentă")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message(
                embed=error_embed("Nu se redă nimic."), ephemeral=True
            )
        vc.pause()
        await interaction.response.send_message(embed=success_embed("⏸️ Pauză."))

    @app_commands.command(name="resume", description="Continuă melodia")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_paused():
            return await interaction.response.send_message(
                embed=error_embed("Muzica nu este în pauză."), ephemeral=True
            )
        vc.resume()
        await interaction.response.send_message(embed=success_embed("▶️ Continuă!"))

    @app_commands.command(name="stop", description="Oprește muzica și golește coada")
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(
                embed=error_embed("Botul nu este în niciun canal vocal."), ephemeral=True
            )
        player = self.get_player(interaction)
        player.queue.clear()
        player.current = None
        vc.stop()
        await interaction.response.send_message(embed=success_embed("⏹️ Muzică oprită și coadă golită."))

    @app_commands.command(name="queue", description="Afișează coada de melodii")
    async def queue_cmd(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if not player.current and not player.queue:
            return await interaction.response.send_message(
                embed=embed(
                    title="📋 Coadă goală",
                    description="Nu există melodii în coadă.",
                    color=config.COLOR_PRIMARY,
                )
            )
        lines = []
        if player.current:
            lines.append(
                f"**▶️ Acum:** [{player.current.title}]({player.current.webpage_url}) `{player.current.duration_str()}`"
            )
        for i, song in enumerate(player.queue[:10], 1):
            lines.append(
                f"`{i}.` [{song.title}]({song.webpage_url}) `{song.duration_str()}`"
            )
        if len(player.queue) > 10:
            lines.append(f"_...și încă {len(player.queue) - 10} melodii_")
        e = embed(
            title=f"📋 Coadă — {len(player.queue)} melodii",
            description="\n".join(lines),
            color=config.COLOR_PRIMARY,
            fields=[
                ("🔁 Loop", "Da" if player.loop else "Nu", True),
                ("🔊 Volum", f"{int(player.volume * 100)}%", True),
            ],
        )
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="nowplaying", description="Afișează melodia curentă")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        if not player.current:
            return await interaction.response.send_message(
                embed=error_embed("Nu se redă nimic."), ephemeral=True
            )
        song = player.current
        e = embed(
            title="🎵 Redare acum",
            description=f"**[{song.title}]({song.webpage_url})**",
            color=config.COLOR_PRIMARY,
            thumbnail=song.thumbnail,
            fields=[
                ("⏱️ Durată", song.duration_str(), True),
                ("👤 Uploader", song.uploader, True),
                ("👤 Cerut de", song.requester.display_name if song.requester else "?", True),
                ("🔊 Volum", f"{int(player.volume * 100)}%", True),
                ("🔁 Loop", "Da" if player.loop else "Nu", True),
            ],
        )
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="volume", description="Setează volumul (0-100)")
    @app_commands.describe(level="Nivelul volumului (0-100)")
    async def volume(self, interaction: discord.Interaction, level: int):
        if not 0 <= level <= 100:
            return await interaction.response.send_message(
                embed=error_embed("Volumul trebuie să fie între 0 și 100."), ephemeral=True
            )
        player = self.get_player(interaction)
        player.volume = level / 100
        vc = interaction.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = player.volume
        await interaction.response.send_message(
            embed=success_embed(f"🔊 Volum setat la **{level}%**.")
        )

    @app_commands.command(name="loop", description="Activează/dezactivează loop pentru melodia curentă")
    async def loop_cmd(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        player.loop = not player.loop
        status = "activat ✅" if player.loop else "dezactivat ❌"
        await interaction.response.send_message(
            embed=success_embed(f"🔁 Loop {status}.")
        )

    @app_commands.command(name="shuffle", description="Amestecă coada de melodii")
    async def shuffle(self, interaction: discord.Interaction):
        import random

        player = self.get_player(interaction)
        if len(player.queue) < 2:
            return await interaction.response.send_message(
                embed=error_embed("Coada are prea puține melodii pentru amestecat."), ephemeral=True
            )
        random.shuffle(player.queue)
        await interaction.response.send_message(
            embed=success_embed(f"🔀 Coadă amestecată! ({len(player.queue)} melodii)")
        )


async def setup(bot):
    await bot.add_cog(Music(bot))
