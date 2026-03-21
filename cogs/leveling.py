import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
from discord.ext import tasks
import random

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed


LEVEL_ROLES = {
    5:  None,   # Fill in role IDs or leave None
    10: None,
    20: None,
    30: None,
    50: None,
}

VOICE_XP_INTERVAL   = 5      # minutes between voice XP grants
VOICE_XP_PER_GRANT  = 20     # XP per grant for being in voice
AFK_CHANNEL_NAMES   = {"afk", "AFK", "away"}   # skip XP in these channels


class Leveling(commands.Cog, name="Nivele"):
    """Sistem de XP și nivele (mesaje + voice)."""

    def __init__(self, bot):
        self.bot = bot
        # {(user_id, guild_id): join_datetime}
        self._voice_sessions: dict[tuple, datetime] = {}
        self.grant_voice_xp.start()

    def cog_unload(self):
        self.grant_voice_xp.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        now = datetime.now(timezone.utc)

        data = await db.get_leveling(user_id, guild_id)

        # Cooldown check
        if data["last_xp_time"]:
            last = datetime.fromisoformat(data["last_xp_time"])
            if (now - last).total_seconds() < config.XP_COOLDOWN_SECONDS:
                return

        xp_gain = random.randint(config.XP_PER_MESSAGE_MIN, config.XP_PER_MESSAGE_MAX)

        # Check XP boost
        if data.get("xp_boost_until"):
            boost_end = datetime.fromisoformat(data["xp_boost_until"])
            if now < boost_end:
                xp_gain *= 2

        updated = await db.add_xp(user_id, guild_id, xp_gain)
        await db.update_last_xp_time(user_id, guild_id, now.isoformat())

        new_level = updated["level"]
        current_xp = updated["xp"]

        # Check level up
        while current_xp >= config.xp_for_level(new_level + 1):
            new_level += 1

        if new_level > updated["level"]:
            await db.set_level(user_id, guild_id, new_level)
            await self._handle_level_up(message.author, message.guild, new_level)

    async def _handle_level_up(self, member: discord.Member, guild: discord.Guild, new_level: int):
        settings = await db.get_guild_settings(guild.id)
        ch_id = settings.get("level_channel") or config.LEVEL_UP_CHANNEL_ID
        ch = guild.get_channel(ch_id) if ch_id else None

        e = embed(
            title="🎉 Level Up!",
            description=f"Felicitări {member.mention}! Ai ajuns la **Level {new_level}**!",
            color=config.COLOR_LEVEL,
        )
        e.set_thumbnail(url=member.display_avatar.url)

        if ch:
            await ch.send(embed=e)
        else:
            try:
                await member.send(embed=e)
            except Exception:
                pass

        # Assign level role if configured
        role_id = LEVEL_ROLES.get(new_level)
        if role_id:
            role = guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason=f"Level {new_level} atins")
                except Exception:
                    pass

    # ─── Voice XP listeners ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                     before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        key = (member.id, member.guild.id)
        # Joined a voice channel
        if after.channel and not before.channel:
            if after.channel.name not in AFK_CHANNEL_NAMES:
                self._voice_sessions[key] = datetime.now(timezone.utc)
        # Left voice channel
        elif before.channel and not after.channel:
            self._voice_sessions.pop(key, None)
        # Moved channels
        elif before.channel and after.channel and before.channel != after.channel:
            if after.channel.name in AFK_CHANNEL_NAMES:
                self._voice_sessions.pop(key, None)
            else:
                if key not in self._voice_sessions:
                    self._voice_sessions[key] = datetime.now(timezone.utc)

    @tasks.loop(minutes=VOICE_XP_INTERVAL)
    async def grant_voice_xp(self):
        """Award XP to all users currently in non-AFK voice channels."""
        for (user_id, guild_id), join_time in list(self._voice_sessions.items()):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            member = guild.get_member(user_id)
            if not member or not member.voice:
                self._voice_sessions.pop((user_id, guild_id), None)
                continue
            # Skip muted/deafened if desired (optional)
            if member.voice.self_deaf or member.voice.afk:
                continue

            xp_gain = VOICE_XP_PER_GRANT
            updated = await db.add_xp(user_id, guild_id, xp_gain)
            new_level = updated["level"]
            current_xp = updated["xp"]
            while current_xp >= config.xp_for_level(new_level + 1):
                new_level += 1
            if new_level > updated["level"]:
                await db.set_level(user_id, guild_id, new_level)
                await self._handle_level_up(member, guild, new_level)

    @grant_voice_xp.before_loop
    async def before_voice_xp(self):
        await self.bot.wait_until_ready()

    # ─── /rank ───────────────────────────────────────────────────────────────

    @app_commands.command(name="rank", description="Afișează nivelul tău sau al altui utilizator")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        data = await db.get_leveling(target.id, interaction.guild.id)

        level = data["level"]
        xp = data["xp"]
        xp_needed = config.xp_for_level(level + 1)
        xp_current_level = config.xp_for_level(level)
        xp_progress = xp - xp_current_level
        xp_required = xp_needed - xp_current_level
        bar_len = 20
        filled = int(bar_len * xp_progress / max(xp_required, 1))
        bar = "█" * filled + "░" * (bar_len - filled)

        lb = await db.get_level_leaderboard(interaction.guild.id, 100)
        rank_pos = next((i + 1 for i, r in enumerate(lb) if r["user_id"] == target.id), "?")

        e = embed(
            title=f"⭐ Rank — {target.display_name}",
            color=config.COLOR_LEVEL,
            fields=[
                ("🏆 Nivel", f"**{level}**", True),
                ("✨ XP Total", f"**{xp:,}**", True),
                ("📊 Rank", f"**#{rank_pos}**", True),
                ("💬 Mesaje", f"**{data['messages']:,}**", True),
                ("📈 Progres XP", f"`[{bar}]`\n{xp_progress:,} / {xp_required:,} XP", False),
            ],
        )
        e.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=e)

    # ─── /leaderboard (levels) ───────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="Top 10 membrii cu cele mai mari nivele")
    async def leaderboard(self, interaction: discord.Interaction):
        lb = await db.get_level_leaderboard(interaction.guild.id)
        if not lb:
            return await interaction.response.send_message(
                embed=error_embed("Nu există date de nivel încă."), ephemeral=True
            )
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(lb):
            user = interaction.guild.get_member(row["user_id"])
            name = user.display_name if user else f"ID:{row['user_id']}"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — Level **{row['level']}** | {row['xp']:,} XP")
        await interaction.response.send_message(embed=embed(
            title="🏆 Leaderboard Nivele — GDP Community",
            description="\n".join(lines),
            color=config.COLOR_LEVEL
        ))

    # ─── /setxp (admin) ──────────────────────────────────────────────────────

    @app_commands.command(name="setxp", description="[Admin] Setează XP-ul unui utilizator")
    @app_commands.describe(member="Utilizatorul", xp="Valoarea XP")
    @app_commands.checks.has_permissions(administrator=True)
    async def setxp(self, interaction: discord.Interaction, member: discord.Member, xp: int):
        from utils.database import DB_PATH
        async with __import__("aiosqlite").connect(DB_PATH) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO leveling (user_id, guild_id) VALUES (?,?)",
                (member.id, interaction.guild.id)
            )
            await conn.execute(
                "UPDATE leveling SET xp=? WHERE user_id=? AND guild_id=?",
                (xp, member.id, interaction.guild.id)
            )
            await conn.commit()
        await interaction.response.send_message(
            embed=success_embed(f"XP-ul lui {member.mention} setat la **{xp:,}**.")
        )


async def setup(bot):
    await bot.add_cog(Leveling(bot))
