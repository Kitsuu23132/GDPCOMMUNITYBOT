import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import json
import re

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed, warning_embed

# URL regex
URL_REGEX = re.compile(
    r"(https?://|www\.)\S+", re.IGNORECASE
)

class AutoMod(commands.Cog, name="AutoMod"):
    """Sistem automat de moderare."""

    def __init__(self, bot):
        self.bot = bot
        # In-memory spam tracker: {guild_id: {user_id: [timestamps]}}
        self._spam_tracker: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    # ─── Main message listener ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.manage_messages:
            return

        cfg = await db.get_automod_config(message.guild.id)
        if not cfg["enabled"]:
            return

        # Whitelist channels
        if cfg["whitelist_channels"]:
            wl_channels = json.loads(cfg["whitelist_channels"])
            if message.channel.id in wl_channels:
                return

        # Whitelist roles
        if cfg["whitelist_roles"]:
            wl_roles = json.loads(cfg["whitelist_roles"])
            if any(r.id in wl_roles for r in message.author.roles):
                return

        violation = None

        # ── Anti-spam ──
        if cfg["anti_spam"]:
            now = datetime.now(timezone.utc).timestamp()
            uid = message.author.id
            gid = message.guild.id
            self._spam_tracker[gid][uid].append(now)
            # Keep only timestamps within interval
            interval = cfg["spam_interval"]
            self._spam_tracker[gid][uid] = [
                t for t in self._spam_tracker[gid][uid] if now - t <= interval
            ]
            if len(self._spam_tracker[gid][uid]) >= cfg["spam_threshold"]:
                violation = "spam"
                self._spam_tracker[gid][uid].clear()

        # ── Anti-links ──
        if not violation and cfg["anti_links"] and URL_REGEX.search(message.content):
            allowed = json.loads(cfg["allowed_domains"]) if cfg["allowed_domains"] else []
            is_allowed = any(domain in message.content for domain in allowed) if allowed else False
            if not is_allowed:
                violation = "link neautorizat"

        # ── Anti-caps ──
        if not violation and cfg["anti_caps"] and len(message.content) > 10:
            caps = sum(1 for c in message.content if c.isupper())
            total_alpha = sum(1 for c in message.content if c.isalpha())
            if total_alpha > 0 and (caps / total_alpha * 100) >= cfg["caps_threshold"]:
                violation = "caps lock excesiv"

        # ── Anti-mentions ──
        if not violation and cfg["anti_mentions"]:
            mention_count = len(message.mentions) + len(message.role_mentions)
            if mention_count >= cfg["max_mentions"]:
                violation = f"spam mențiuni ({mention_count})"

        # ── Bad words ──
        if not violation and cfg["bad_words"]:
            bad_list = json.loads(cfg["bad_words"])
            content_lower = message.content.lower()
            for word in bad_list:
                if word.lower() in content_lower:
                    violation = f"cuvânt interzis"
                    break

        if not violation:
            return

        # Delete message
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        await self._apply_action(message, cfg, violation)

    async def _apply_action(self, message: discord.Message, cfg: dict, violation: str):
        member = message.author
        guild = message.guild
        action = cfg["action"]

        # Notify in channel
        try:
            notify = await message.channel.send(embed=embed(
                title="🤖 AutoMod",
                description=f"{member.mention} **Mesaj șters** — {violation}",
                color=config.COLOR_WARNING
            ))
            import asyncio
            await asyncio.sleep(5)
            await notify.delete()
        except Exception:
            pass

        if action == "warn":
            await db.add_warning(member.id, guild.id, self.bot.user.id,
                                  f"[AutoMod] {violation}", now_iso())
        elif action == "mute":
            try:
                until = discord.utils.utcnow() + timedelta(seconds=cfg["mute_duration"])
                await member.timeout(until, reason=f"[AutoMod] {violation}")
            except discord.Forbidden:
                pass
        elif action == "kick":
            try:
                await member.kick(reason=f"[AutoMod] {violation}")
            except discord.Forbidden:
                pass
        elif action == "ban":
            try:
                await member.ban(reason=f"[AutoMod] {violation}", delete_message_days=1)
            except discord.Forbidden:
                pass

        # Log to automod channel
        log_ch_id = cfg["log_channel"]
        if log_ch_id:
            log_ch = guild.get_channel(log_ch_id)
            if log_ch:
                e = embed(
                    title="🤖 AutoMod — Acțiune",
                    color=config.COLOR_WARNING,
                    fields=[
                        ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                        ("Canal", message.channel.mention, True),
                        ("Motiv", violation, True),
                        ("Acțiune", action.upper(), True),
                        ("Conținut", f"```{message.content[:500]}```", False),
                    ]
                )
                e.set_thumbnail(url=member.display_avatar.url)
                await log_ch.send(embed=e)

    # ─── /automod commands ───────────────────────────────────────────────────

    automod_group = app_commands.Group(name="automod", description="Configurare AutoMod")

    @automod_group.command(name="status", description="Afișează configurația AutoMod")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_status(self, interaction: discord.Interaction):
        cfg = await db.get_automod_config(interaction.guild.id)
        bad_words = json.loads(cfg["bad_words"]) if cfg["bad_words"] else []
        e = embed(
            title="🤖 Configurație AutoMod",
            color=config.COLOR_PRIMARY,
            fields=[
                ("✅ Activat", "Da" if cfg["enabled"] else "Nu", True),
                ("🚫 Anti-Spam", f"Da ({cfg['spam_threshold']} msg/{cfg['spam_interval']}s)" if cfg["anti_spam"] else "Nu", True),
                ("🔗 Anti-Links", "Da" if cfg["anti_links"] else "Nu", True),
                ("🔠 Anti-Caps", f"Da (>{cfg['caps_threshold']}%)" if cfg["anti_caps"] else "Nu", True),
                ("📣 Anti-Mențiuni", f"Da (max {cfg['max_mentions']})" if cfg["anti_mentions"] else "Nu", True),
                ("🤬 Bad Words", f"{len(bad_words)} cuvinte", True),
                ("⚡ Acțiune", cfg["action"].upper(), True),
                ("⏱️ Durată mute", f"{cfg['mute_duration']}s", True),
            ]
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @automod_group.command(name="toggle", description="Activează/dezactivează AutoMod")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_toggle(self, interaction: discord.Interaction):
        cfg = await db.get_automod_config(interaction.guild.id)
        new_val = 0 if cfg["enabled"] else 1
        await db.update_automod_config(interaction.guild.id, "enabled", new_val)
        status = "activat ✅" if new_val else "dezactivat ❌"
        await interaction.response.send_message(embed=success_embed(f"AutoMod {status}."))

    @automod_group.command(name="action", description="Setează acțiunea pentru violări")
    @app_commands.describe(action="warn / mute / kick / ban")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_action(self, interaction: discord.Interaction, action: str):
        if action not in ("warn", "mute", "kick", "ban"):
            return await interaction.response.send_message(
                embed=error_embed("Acțiuni valide: `warn`, `mute`, `kick`, `ban`"), ephemeral=True
            )
        await db.update_automod_config(interaction.guild.id, "action", action)
        await interaction.response.send_message(
            embed=success_embed(f"Acțiunea AutoMod setată la **{action.upper()}**.")
        )

    @automod_group.command(name="antispam", description="Configurare anti-spam")
    @app_commands.describe(threshold="Număr mesaje", interval="Interval secunde")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_antispam(self, interaction: discord.Interaction,
                                threshold: int = 5, interval: int = 5):
        await db.update_automod_config(interaction.guild.id, "spam_threshold", threshold)
        await db.update_automod_config(interaction.guild.id, "spam_interval", interval)
        await db.update_automod_config(interaction.guild.id, "anti_spam", 1)
        await interaction.response.send_message(
            embed=success_embed(f"Anti-spam activat: **{threshold}** mesaje în **{interval}s**.")
        )

    @automod_group.command(name="antilinks", description="Activează/dezactivează filtrarea link-urilor")
    @app_commands.describe(enabled="True/False")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_antilinks(self, interaction: discord.Interaction, enabled: bool):
        await db.update_automod_config(interaction.guild.id, "anti_links", 1 if enabled else 0)
        await interaction.response.send_message(
            embed=success_embed(f"Anti-links {'activat ✅' if enabled else 'dezactivat ❌'}.")
        )

    @automod_group.command(name="anticaps", description="Configurare anti-caps")
    @app_commands.describe(threshold="Procentaj maxim majuscule (0-100)")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_anticaps(self, interaction: discord.Interaction, threshold: int = 70):
        await db.update_automod_config(interaction.guild.id, "caps_threshold", threshold)
        await db.update_automod_config(interaction.guild.id, "anti_caps", 1)
        await interaction.response.send_message(
            embed=success_embed(f"Anti-caps activat: max **{threshold}%** majuscule.")
        )

    @automod_group.command(name="antimentions", description="Setează limita de mențiuni per mesaj")
    @app_commands.describe(max_mentions="Număr maxim de mențiuni")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_antimentions(self, interaction: discord.Interaction, max_mentions: int = 5):
        await db.update_automod_config(interaction.guild.id, "max_mentions", max_mentions)
        await db.update_automod_config(interaction.guild.id, "anti_mentions", 1)
        await interaction.response.send_message(
            embed=success_embed(f"Anti-mențiuni activat: max **{max_mentions}** mențiuni/mesaj.")
        )

    @automod_group.command(name="addword", description="Adaugă un cuvânt interzis")
    @app_commands.describe(word="Cuvântul de adăugat")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_addword(self, interaction: discord.Interaction, word: str):
        cfg = await db.get_automod_config(interaction.guild.id)
        bad_words = json.loads(cfg["bad_words"]) if cfg["bad_words"] else []
        word = word.lower().strip()
        if word in bad_words:
            return await interaction.response.send_message(
                embed=error_embed(f"Cuvântul `{word}` există deja."), ephemeral=True
            )
        bad_words.append(word)
        await db.update_automod_config(interaction.guild.id, "bad_words", json.dumps(bad_words))
        await interaction.response.send_message(
            embed=success_embed(f"Cuvântul `{word}` adăugat. Total: **{len(bad_words)}**.")
        )

    @automod_group.command(name="removeword", description="Elimină un cuvânt interzis")
    @app_commands.describe(word="Cuvântul de eliminat")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_removeword(self, interaction: discord.Interaction, word: str):
        cfg = await db.get_automod_config(interaction.guild.id)
        bad_words = json.loads(cfg["bad_words"]) if cfg["bad_words"] else []
        word = word.lower().strip()
        if word not in bad_words:
            return await interaction.response.send_message(
                embed=error_embed(f"Cuvântul `{word}` nu există în listă."), ephemeral=True
            )
        bad_words.remove(word)
        await db.update_automod_config(interaction.guild.id, "bad_words", json.dumps(bad_words))
        await interaction.response.send_message(
            embed=success_embed(f"Cuvântul `{word}` eliminat.")
        )

    @automod_group.command(name="setlogchannel", description="Setează canalul de log AutoMod")
    @app_commands.describe(channel="Canalul de log")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_automod_config(interaction.guild.id, "log_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Log AutoMod setat la {channel.mention}.")
        )

    @automod_group.command(name="whitelistchannel", description="Adaugă/elimină un canal din whitelist")
    @app_commands.describe(channel="Canalul")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_wl_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        cfg = await db.get_automod_config(interaction.guild.id)
        wl = json.loads(cfg["whitelist_channels"]) if cfg["whitelist_channels"] else []
        if channel.id in wl:
            wl.remove(channel.id)
            msg = f"{channel.mention} eliminat din whitelist."
        else:
            wl.append(channel.id)
            msg = f"{channel.mention} adăugat în whitelist."
        await db.update_automod_config(interaction.guild.id, "whitelist_channels", json.dumps(wl))
        await interaction.response.send_message(embed=success_embed(msg))


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
