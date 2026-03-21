import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import asyncio
import yt_dlp
import functools

import config
from utils.helpers import embed, success_embed, error_embed

# ─── IMPORTANT ───────────────────────────────────────────────────────────────
# FFmpeg trebuie instalat separat: https://ffmpeg.org/download.html
# Adaugă FFmpeg în PATH sau setează FFMPEG_PATH mai jos.
FFMPEG_PATH = "ffmpeg"   # schimbă cu calea completă dacă nu e în PATH
# ─────────────────────────────────────────────────────────────────────────────

YTDL_OPTIONS = {
    "format": "bestaudio[ext=m4a]/bestaudio/best",
    "noplaylist": True,
    "nocheckcertificate": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1",
    "source_address": "0.0.0.0",
    "extract_flat": False,
}

FFMPEG_OPTIONS = {
    "executable": FFMPEG_PATH,
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


class Song:
    def __init__(self, data: dict):
        self.title       = data.get("title", "Unknown")
        # URL direct de stream — poate fi în url sau în requested_formats
        self.url         = data.get("url") or ""
        if not self.url and data.get("requested_formats"):
            self.url = data["requested_formats"][0].get("url", "")
        if not self.url and data.get("formats"):
            for f in data["formats"]:
                if f.get("url") and f.get("vcodec") == "none":
                    self.url = f["url"]
                    break
        self.webpage_url = data.get("webpage_url", data.get("url", ""))
        self.duration    = data.get("duration", 0)
        self.thumbnail   = data.get("thumbnail", "")
        self.uploader    = data.get("uploader", "Unknown")
        self.requester   = None   # set after creation

    def duration_str(self) -> str:
        if not self.duration:
            return "LIVE"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class MusicPlayer:
    """Per-guild music state."""

    def __init__(self, ctx_or_inter):
        self.guild      = ctx_or_inter.guild
        self.channel    = ctx_or_inter.channel
        self.queue: list[Song] = []
        self.current: Song | None = None
        self.volume     = 0.5
        self.loop       = False
        self._vc: discord.VoiceClient | None = None

    @property
    def vc(self) -> discord.VoiceClient | None:
        return self.guild.voice_client


async def fetch_song(query: str, loop: asyncio.AbstractEventLoop) -> Song | None:
    ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
    try:
        partial = functools.partial(ytdl.extract_info, query, download=False)
        data = await loop.run_in_executor(None, partial)
        if "entries" in data:
            data = data["entries"][0]
        return Song(data)
    except Exception:
        return None


class Music(commands.Cog, name="Muzică"):
    """Sistem de muzică pentru canale vocale."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}

    def get_player(self, interaction: discord.Interaction) -> MusicPlayer:
        if interaction.guild.id not in self.players:
            self.players[interaction.guild.id] = MusicPlayer(interaction)
        return self.players[interaction.guild.id]

    def destroy_player(self, guild_id: int):
        self.players.pop(guild_id, None)

    # ─── /join ───────────────────────────────────────────────────────────────

    @app_commands.command(name="join", description="Botul intră în canalul tău vocal")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message(
                embed=error_embed("Trebuie să fii într-un canal vocal!"), ephemeral=True
            )
        vc = interaction.guild.voice_client
        if vc:
            await vc.move_to(interaction.user.voice.channel)
        else:
            await interaction.user.voice.channel.connect()
        await interaction.response.send_message(
            embed=success_embed(f"Conectat în **{interaction.user.voice.channel.name}**! 🎵")
        )

    # ─── /leave ──────────────────────────────────────────────────────────────

    @app_commands.command(name="leave", description="Botul iese din canalul vocal")
    async def leave(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message(
                embed=error_embed("Botul nu este în niciun canal vocal."), ephemeral=True
            )
        self.destroy_player(interaction.guild.id)
        await vc.disconnect()
        await interaction.response.send_message(embed=success_embed("Deconectat! 👋"))

    # ─── /play ───────────────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Redă o melodie (URL YouTube sau termen de căutare)")
    @app_commands.describe(query="Link YouTube sau numele melodiei")
    async def play(self, interaction: discord.Interaction, query: str):
        if not interaction.user.voice:
            return await interaction.response.send_message(
                embed=error_embed("Trebuie să fii într-un canal vocal!"), ephemeral=True
            )

        await interaction.response.defer()

        # Connect if needed
        vc = interaction.guild.voice_client
        if not vc:
            vc = await interaction.user.voice.channel.connect()
        elif interaction.user.voice.channel != vc.channel:
            await vc.move_to(interaction.user.voice.channel)

        player = self.get_player(interaction)

        song = await fetch_song(query, self.bot.loop)
        if not song:
            return await interaction.followup.send(
                embed=error_embed("Nu am putut găsi melodia. Verifică link-ul sau termenul de căutare.")
            )
        if not song.url or not song.url.startswith(("http://", "https://")):
            return await interaction.followup.send(
                embed=error_embed(
                    "Nu am obținut un link valid de redare. Încearcă alt link sau altă căutare."
                )
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
                ]
            )
            await interaction.followup.send(embed=e)
        else:
            player.current = song
            try:
                source = discord.FFmpegPCMAudio(song.url, **FFMPEG_OPTIONS)
                source = discord.PCMVolumeTransformer(source, volume=player.volume)
            except Exception as err:
                return await interaction.followup.send(
                    embed=error_embed(
                        "Nu am putut pregăti sursa audio. Verifică că **FFmpeg** este instalat și în PATH.\n"
                        f"_(Eroare: {err})_"
                    )
                )

            def after(error):
                if error:
                    print(f"[Music] Player error: {error}")
                asyncio.run_coroutine_threadsafe(self._play_next(interaction.guild), self.bot.loop)

            try:
                vc.play(source, after=after)
            except discord.ClientException as err:
                return await interaction.followup.send(
                    embed=error_embed(f"Eroare la redare: {err}. Botul rămâne în canal.")
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
                ]
            )
            await interaction.followup.send(embed=e)

    async def _play_next(self, guild: discord.Guild):
        player = self.players.get(guild.id)
        if not player:
            return
        vc = guild.voice_client
        if not vc:
            return

        if player.loop and player.current:
            song = player.current
        elif player.queue:
            song = player.queue.pop(0)
            player.current = song
        else:
            player.current = None
            return

        if not song.url or not song.url.startswith(("http://", "https://")):
            # URL invalid — trecem la următoarea
            return await self._play_next(guild)

        try:
            source = discord.FFmpegPCMAudio(song.url, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=player.volume)
        except Exception as err:
            print(f"[Music] _play_next source error: {err}")
            return await self._play_next(guild)

        def after(error):
            if error:
                print(f"[Music] _play_next after error: {error}")
            asyncio.run_coroutine_threadsafe(self._play_next(guild), self.bot.loop)

        try:
            vc.play(source, after=after)
        except discord.ClientException as err:
            print(f"[Music] _play_next play error: {err}")
            return await self._play_next(guild)

        e = embed(
            title="🎵 Redare acum",
            description=f"**[{song.title}]({song.webpage_url})**",
            color=config.COLOR_PRIMARY,
            thumbnail=song.thumbnail,
            fields=[("⏱️ Durată", song.duration_str(), True)]
        )
        try:
            await player.channel.send(embed=e)
        except Exception:
            pass

    # ─── /skip ───────────────────────────────────────────────────────────────

    @app_commands.command(name="skip", description="Treci la melodia următoare")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message(
                embed=error_embed("Nu se redă nimic."), ephemeral=True
            )
        vc.stop()
        await interaction.response.send_message(embed=success_embed("⏭️ Melodie trecută!"))

    # ─── /pause / /resume ────────────────────────────────────────────────────

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

    # ─── /stop ───────────────────────────────────────────────────────────────

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

    # ─── /queue ──────────────────────────────────────────────────────────────

    @app_commands.command(name="queue", description="Afișează coada de melodii")
    async def queue_cmd(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        vc = interaction.guild.voice_client

        if not player.current and not player.queue:
            return await interaction.response.send_message(
                embed=embed(title="📋 Coadă goală", description="Nu există melodii în coadă.", color=config.COLOR_PRIMARY)
            )

        lines = []
        if player.current:
            lines.append(f"**▶️ Acum:** [{player.current.title}]({player.current.webpage_url}) `{player.current.duration_str()}`")

        for i, song in enumerate(player.queue[:10], 1):
            lines.append(f"`{i}.` [{song.title}]({song.webpage_url}) `{song.duration_str()}`")

        if len(player.queue) > 10:
            lines.append(f"_...și încă {len(player.queue) - 10} melodii_")

        e = embed(
            title=f"📋 Coadă — {len(player.queue)} melodii",
            description="\n".join(lines),
            color=config.COLOR_PRIMARY,
            fields=[("🔁 Loop", "Da" if player.loop else "Nu", True),
                    ("🔊 Volum", f"{int(player.volume * 100)}%", True)]
        )
        await interaction.response.send_message(embed=e)

    # ─── /nowplaying ─────────────────────────────────────────────────────────

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
            ]
        )
        await interaction.response.send_message(embed=e)

    # ─── /volume ─────────────────────────────────────────────────────────────

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
        if vc and vc.source:
            vc.source.volume = player.volume
        await interaction.response.send_message(
            embed=success_embed(f"🔊 Volum setat la **{level}%**.")
        )

    # ─── /loop ───────────────────────────────────────────────────────────────

    @app_commands.command(name="loop", description="Activează/dezactivează loop pentru melodia curentă")
    async def loop(self, interaction: discord.Interaction):
        player = self.get_player(interaction)
        player.loop = not player.loop
        status = "activat ✅" if player.loop else "dezactivat ❌"
        await interaction.response.send_message(
            embed=success_embed(f"🔁 Loop {status}.")
        )

    # ─── /shuffle ────────────────────────────────────────────────────────────

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

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                     before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        vc = member.guild.voice_client
        if not vc:
            return
        # Auto-disconnect when alone
        if vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
            await asyncio.sleep(30)
            if vc.channel and len([m for m in vc.channel.members if not m.bot]) == 0:
                self.destroy_player(member.guild.id)
                await vc.disconnect()


async def setup(bot):
    await bot.add_cog(Music(bot))
