<<<<<<< HEAD
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from collections import defaultdict

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed, warning_embed


class AntiRaid(commands.Cog, name="Anti-Raid"):
    """Protecție anti-raid automată."""

    def __init__(self, bot):
        self.bot = bot
        # {guild_id: [join_timestamp, ...]}
        self._join_tracker: dict[int, list[float]] = defaultdict(list)
        # {guild_id: bool} — active lockdown state in memory
        self._lockdown_state: dict[int, bool] = {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await db.get_antiraid_config(member.guild.id)
        if not cfg["enabled"]:
            return

        now = datetime.now(timezone.utc).timestamp()
        gid = member.guild.id

        self._join_tracker[gid].append(now)
        # Keep only joins within interval
        interval = cfg["join_interval"]
        self._join_tracker[gid] = [t for t in self._join_tracker[gid] if now - t <= interval]

        if len(self._join_tracker[gid]) >= cfg["join_threshold"]:
            self._join_tracker[gid].clear()
            await self._trigger_raid_response(member.guild, cfg)

    async def _trigger_raid_response(self, guild: discord.Guild, cfg: dict):
        if self._lockdown_state.get(guild.id):
            return  # Already in lockdown

        self._lockdown_state[guild.id] = True
        await db.update_antiraid_config(guild.id, "lockdown_active", 1)

        action = cfg["action"]
        alert_ch_id = cfg["alert_channel"]

        alert_embed = embed(
            title="🚨 RAID DETECTAT!",
            description=(
                f"**Acțiune aplicată:** {action.upper()}\n"
                f"**Prag depăşit:** {cfg['join_threshold']} join-uri în {cfg['join_interval']}s\n\n"
                f"Serverul a intrat în **modul de protecție**!\n"
                f"Foloseşte `/antiraid lockdown off` pentru a dezactiva."
            ),
            color=config.COLOR_ERROR
        )

        if action == "lockdown":
            # Raise verification level to highest
            try:
                await guild.edit(
                    verification_level=discord.VerificationLevel.highest,
                    reason="[AntiRaid] Raid detectat — lockdown activat"
                )
            except discord.Forbidden:
                pass

        elif action in ("kick", "ban"):
            # Kick/ban recent joiners (last 60 seconds)
            now = datetime.now(timezone.utc).timestamp()
            recent_members = [
                m for m in guild.members
                if m.joined_at and (now - m.joined_at.replace(tzinfo=timezone.utc).timestamp()) <= 60
                and not m.bot
            ]
            for m in recent_members:
                try:
                    if action == "kick":
                        await m.kick(reason="[AntiRaid] Raid detectat")
                    else:
                        await m.ban(reason="[AntiRaid] Raid detectat", delete_message_days=1)
                except Exception:
                    pass

        # Send alert
        if alert_ch_id:
            alert_ch = guild.get_channel(alert_ch_id)
            if alert_ch:
                # Ping admins
                admin_mentions = " ".join(
                    m.mention for m in guild.members
                    if m.guild_permissions.administrator and not m.bot
                )
                await alert_ch.send(
                    content=admin_mentions[:1990] if admin_mentions else None,
                    embed=alert_embed
                )

    antiraid_group = app_commands.Group(name="antiraid", description="Configurare Anti-Raid")

    # ─── /antiraid lockdown ──────────────────────────────────────────────────

    @antiraid_group.command(name="lockdown", description="Activează/dezactivează lockdown manual")
    @app_commands.describe(mode="on / off")
    @app_commands.checks.has_permissions(administrator=True)
    async def raidmode(self, interaction: discord.Interaction, mode: str):
        mode = mode.lower()
        if mode not in ("on", "off"):
            return await interaction.response.send_message(
                embed=error_embed("Foloseşte `on` sau `off`."), ephemeral=True
            )

        if mode == "on":
            self._lockdown_state[interaction.guild.id] = True
            await db.update_antiraid_config(interaction.guild.id, "lockdown_active", 1)
            try:
                await interaction.guild.edit(
                    verification_level=discord.VerificationLevel.highest,
                    reason=f"[AntiRaid] Lockdown manual de {interaction.user}"
                )
            except discord.Forbidden:
                pass
            await interaction.response.send_message(embed=embed(
                title="🔒 Raid Mode ACTIVAT",
                description=(
                    "Serverul este în **lockdown**!\n"
                    "Nivelul de verificare a fost ridicat la maxim.\n"
                    "Foloseşte `/raidmode off` pentru a dezactiva."
                ),
                color=config.COLOR_ERROR
            ))
        else:
            self._lockdown_state[interaction.guild.id] = False
            await db.update_antiraid_config(interaction.guild.id, "lockdown_active", 0)
            try:
                await interaction.guild.edit(
                    verification_level=discord.VerificationLevel.medium,
                    reason=f"[AntiRaid] Lockdown dezactivat de {interaction.user}"
                )
            except discord.Forbidden:
                pass
            await interaction.response.send_message(embed=embed(
                title="🔓 Raid Mode DEZACTIVAT",
                description="Serverul a revenit la normal. Nivelul de verificare a fost resetat.",
                color=config.COLOR_SUCCESS
            ))

    @antiraid_group.command(name="toggle", description="Activează/dezactivează protecția anti-raid")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_toggle(self, interaction: discord.Interaction):
        cfg = await db.get_antiraid_config(interaction.guild.id)
        new_val = 0 if cfg["enabled"] else 1
        await db.update_antiraid_config(interaction.guild.id, "enabled", new_val)
        status = "activată ✅" if new_val else "dezactivată ❌"
        await interaction.response.send_message(
            embed=success_embed(f"Protecție anti-raid {status}.")
        )

    @antiraid_group.command(name="config", description="Configurează pragurile anti-raid")
    @app_commands.describe(
        threshold="Număr join-uri pentru a declanşa (implicit 10)",
        interval="Interval secunde (implicit 10)",
        action="lockdown / kick / ban"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_config(self, interaction: discord.Interaction,
                               threshold: int = 10, interval: int = 10, action: str = "lockdown"):
        if action not in ("lockdown", "kick", "ban"):
            return await interaction.response.send_message(
                embed=error_embed("Acțiuni valide: `lockdown`, `kick`, `ban`"), ephemeral=True
            )
        await db.update_antiraid_config(interaction.guild.id, "join_threshold", threshold)
        await db.update_antiraid_config(interaction.guild.id, "join_interval", interval)
        await db.update_antiraid_config(interaction.guild.id, "action", action)
        await interaction.response.send_message(embed=success_embed(
            f"Anti-raid configurat:\n"
            f"**Prag:** {threshold} join-uri în {interval}s\n"
            f"**Acțiune:** {action.upper()}"
        ))

    @antiraid_group.command(name="setalert", description="Setează canalul de alertă raid")
    @app_commands.describe(channel="Canalul de alertă")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_setalert(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_antiraid_config(interaction.guild.id, "alert_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal alertă raid setat la {channel.mention}.")
        )

    @antiraid_group.command(name="status", description="Afişează statusul anti-raid")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_status(self, interaction: discord.Interaction):
        cfg = await db.get_antiraid_config(interaction.guild.id)
        lockdown = self._lockdown_state.get(interaction.guild.id, bool(cfg["lockdown_active"]))
        await interaction.response.send_message(embed=embed(
            title="🛡️ Status Anti-Raid",
            color=config.COLOR_ERROR if lockdown else config.COLOR_SUCCESS,
            fields=[
                ("✅ Activat", "Da" if cfg["enabled"] else "Nu", True),
                ("🔒 Lockdown activ", "Da ⚠️" if lockdown else "Nu", True),
                ("⚡ Acțiune", cfg["action"].upper(), True),
                ("📊 Prag", f"{cfg['join_threshold']} în {cfg['join_interval']}s", True),
            ]
        ), ephemeral=True)


async def setup(bot):
    await bot.add_cog(AntiRaid(bot))
=======
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from collections import defaultdict

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed, warning_embed


class AntiRaid(commands.Cog, name="Anti-Raid"):
    """Protecție anti-raid automată."""

    def __init__(self, bot):
        self.bot = bot
        # {guild_id: [join_timestamp, ...]}
        self._join_tracker: dict[int, list[float]] = defaultdict(list)
        # {guild_id: bool} — active lockdown state in memory
        self._lockdown_state: dict[int, bool] = {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await db.get_antiraid_config(member.guild.id)
        if not cfg["enabled"]:
            return

        now = datetime.now(timezone.utc).timestamp()
        gid = member.guild.id

        self._join_tracker[gid].append(now)
        # Keep only joins within interval
        interval = cfg["join_interval"]
        self._join_tracker[gid] = [t for t in self._join_tracker[gid] if now - t <= interval]

        if len(self._join_tracker[gid]) >= cfg["join_threshold"]:
            self._join_tracker[gid].clear()
            await self._trigger_raid_response(member.guild, cfg)

    async def _trigger_raid_response(self, guild: discord.Guild, cfg: dict):
        if self._lockdown_state.get(guild.id):
            return  # Already in lockdown

        self._lockdown_state[guild.id] = True
        await db.update_antiraid_config(guild.id, "lockdown_active", 1)

        action = cfg["action"]
        alert_ch_id = cfg["alert_channel"]

        alert_embed = embed(
            title="🚨 RAID DETECTAT!",
            description=(
                f"**Acțiune aplicată:** {action.upper()}\n"
                f"**Prag depăşit:** {cfg['join_threshold']} join-uri în {cfg['join_interval']}s\n\n"
                f"Serverul a intrat în **modul de protecție**!\n"
                f"Foloseşte `/antiraid lockdown off` pentru a dezactiva."
            ),
            color=config.COLOR_ERROR
        )

        if action == "lockdown":
            # Raise verification level to highest
            try:
                await guild.edit(
                    verification_level=discord.VerificationLevel.highest,
                    reason="[AntiRaid] Raid detectat — lockdown activat"
                )
            except discord.Forbidden:
                pass

        elif action in ("kick", "ban"):
            # Kick/ban recent joiners (last 60 seconds)
            now = datetime.now(timezone.utc).timestamp()
            recent_members = [
                m for m in guild.members
                if m.joined_at and (now - m.joined_at.replace(tzinfo=timezone.utc).timestamp()) <= 60
                and not m.bot
            ]
            for m in recent_members:
                try:
                    if action == "kick":
                        await m.kick(reason="[AntiRaid] Raid detectat")
                    else:
                        await m.ban(reason="[AntiRaid] Raid detectat", delete_message_days=1)
                except Exception:
                    pass

        # Send alert
        if alert_ch_id:
            alert_ch = guild.get_channel(alert_ch_id)
            if alert_ch:
                # Ping admins
                admin_mentions = " ".join(
                    m.mention for m in guild.members
                    if m.guild_permissions.administrator and not m.bot
                )
                await alert_ch.send(
                    content=admin_mentions[:1990] if admin_mentions else None,
                    embed=alert_embed
                )

    antiraid_group = app_commands.Group(name="antiraid", description="Configurare Anti-Raid")

    # ─── /antiraid lockdown ──────────────────────────────────────────────────

    @antiraid_group.command(name="lockdown", description="Activează/dezactivează lockdown manual")
    @app_commands.describe(mode="on / off")
    @app_commands.checks.has_permissions(administrator=True)
    async def raidmode(self, interaction: discord.Interaction, mode: str):
        mode = mode.lower()
        if mode not in ("on", "off"):
            return await interaction.response.send_message(
                embed=error_embed("Foloseşte `on` sau `off`."), ephemeral=True
            )

        if mode == "on":
            self._lockdown_state[interaction.guild.id] = True
            await db.update_antiraid_config(interaction.guild.id, "lockdown_active", 1)
            try:
                await interaction.guild.edit(
                    verification_level=discord.VerificationLevel.highest,
                    reason=f"[AntiRaid] Lockdown manual de {interaction.user}"
                )
            except discord.Forbidden:
                pass
            await interaction.response.send_message(embed=embed(
                title="🔒 Raid Mode ACTIVAT",
                description=(
                    "Serverul este în **lockdown**!\n"
                    "Nivelul de verificare a fost ridicat la maxim.\n"
                    "Foloseşte `/raidmode off` pentru a dezactiva."
                ),
                color=config.COLOR_ERROR
            ))
        else:
            self._lockdown_state[interaction.guild.id] = False
            await db.update_antiraid_config(interaction.guild.id, "lockdown_active", 0)
            try:
                await interaction.guild.edit(
                    verification_level=discord.VerificationLevel.medium,
                    reason=f"[AntiRaid] Lockdown dezactivat de {interaction.user}"
                )
            except discord.Forbidden:
                pass
            await interaction.response.send_message(embed=embed(
                title="🔓 Raid Mode DEZACTIVAT",
                description="Serverul a revenit la normal. Nivelul de verificare a fost resetat.",
                color=config.COLOR_SUCCESS
            ))

    @antiraid_group.command(name="toggle", description="Activează/dezactivează protecția anti-raid")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_toggle(self, interaction: discord.Interaction):
        cfg = await db.get_antiraid_config(interaction.guild.id)
        new_val = 0 if cfg["enabled"] else 1
        await db.update_antiraid_config(interaction.guild.id, "enabled", new_val)
        status = "activată ✅" if new_val else "dezactivată ❌"
        await interaction.response.send_message(
            embed=success_embed(f"Protecție anti-raid {status}.")
        )

    @antiraid_group.command(name="config", description="Configurează pragurile anti-raid")
    @app_commands.describe(
        threshold="Număr join-uri pentru a declanşa (implicit 10)",
        interval="Interval secunde (implicit 10)",
        action="lockdown / kick / ban"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_config(self, interaction: discord.Interaction,
                               threshold: int = 10, interval: int = 10, action: str = "lockdown"):
        if action not in ("lockdown", "kick", "ban"):
            return await interaction.response.send_message(
                embed=error_embed("Acțiuni valide: `lockdown`, `kick`, `ban`"), ephemeral=True
            )
        await db.update_antiraid_config(interaction.guild.id, "join_threshold", threshold)
        await db.update_antiraid_config(interaction.guild.id, "join_interval", interval)
        await db.update_antiraid_config(interaction.guild.id, "action", action)
        await interaction.response.send_message(embed=success_embed(
            f"Anti-raid configurat:\n"
            f"**Prag:** {threshold} join-uri în {interval}s\n"
            f"**Acțiune:** {action.upper()}"
        ))

    @antiraid_group.command(name="setalert", description="Setează canalul de alertă raid")
    @app_commands.describe(channel="Canalul de alertă")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_setalert(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_antiraid_config(interaction.guild.id, "alert_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal alertă raid setat la {channel.mention}.")
        )

    @antiraid_group.command(name="status", description="Afişează statusul anti-raid")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_status(self, interaction: discord.Interaction):
        cfg = await db.get_antiraid_config(interaction.guild.id)
        lockdown = self._lockdown_state.get(interaction.guild.id, bool(cfg["lockdown_active"]))
        await interaction.response.send_message(embed=embed(
            title="🛡️ Status Anti-Raid",
            color=config.COLOR_ERROR if lockdown else config.COLOR_SUCCESS,
            fields=[
                ("✅ Activat", "Da" if cfg["enabled"] else "Nu", True),
                ("🔒 Lockdown activ", "Da ⚠️" if lockdown else "Nu", True),
                ("⚡ Acțiune", cfg["action"].upper(), True),
                ("📊 Prag", f"{cfg['join_threshold']} în {cfg['join_interval']}s", True),
            ]
        ), ephemeral=True)


async def setup(bot):
    await bot.add_cog(AntiRaid(bot))
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
