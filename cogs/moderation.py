import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import asyncio

import config
from utils import database as db
from utils.helpers import now_iso, parse_time, format_duration, success_embed, error_embed, embed


class Moderation(commands.Cog, name="Moderare"):
    """Comenzi de moderare pentru staff."""

    def __init__(self, bot):
        self.bot = bot
        self.check_mutes.start()

    def cog_unload(self):
        self.check_mutes.cancel()

    # ─── Helper: log action ──────────────────────────────────────────────────

    async def log_action(self, guild: discord.Guild, action: str, mod: discord.Member,
                         target: discord.Member, reason: str, color: int, extra: str = ""):
        # Construim embed-ul de moderare o singură dată
        e = embed(
            title=f"🔨 {action}",
            color=color,
            fields=[
                ("Utilizator", f"{target.mention} (`{target.id}`)", True),
                ("Moderator", f"{mod.mention} (`{mod.id}`)", True),
                ("Motiv", reason or "Fără motiv", False),
            ] + ([("Detalii", extra, False)] if extra else []),
        )
        e.set_thumbnail(url=target.display_avatar.url)

        # 1) Încercăm să folosim sistemul central de logging (cog-ul "Logging"),
        #    canalul "log-moderare" (tipurile member_ban / member_unban).
        log_cog = self.bot.get_cog("Logging")
        if log_cog and hasattr(log_cog, "_send_log"):
            try:
                # Folosim tipul "member_ban" ca să trimitem toate acțiunile de moderare
                # în canalul de moderare (log-moderare).
                await log_cog._send_log(guild, "member_ban", e)
                return
            except Exception:
                pass

        # 2) Fallback pe vechiul canal de log din setările guild-ului, dacă există.
        settings = await db.get_guild_settings(guild.id)
        log_ch_id = settings.get("log_channel") or config.LOG_CHANNEL_ID
        if not log_ch_id:
            return
        ch = guild.get_channel(log_ch_id)
        if not ch:
            return
        await ch.send(embed=e)

    # ─── /ban ────────────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="Banează un utilizator din server")
    @app_commands.describe(member="Utilizatorul de banat", reason="Motivul", delete_days="Zile de mesaje șterse (0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member,
                  reason: str = "Fără motiv", delete_days: int = 0):
        if member.top_role >= interaction.user.top_role:
            return await interaction.response.send_message(
                embed=error_embed("Nu poți bana un utilizator cu rol mai mare sau egal cu al tău."),
                ephemeral=True
            )
        try:
            await member.send(embed=embed(
                title="🔨 Ai fost banat",
                description=f"Ai fost banat de pe **{interaction.guild.name}**.\n**Motiv:** {reason}",
                color=config.COLOR_ERROR
            ))
        except Exception:
            pass
        await member.ban(reason=f"{interaction.user} | {reason}", delete_message_days=delete_days)
        await interaction.response.send_message(
            embed=success_embed(f"{member.mention} a fost banat.\n**Motiv:** {reason}")
        )
        await self.log_action(interaction.guild, "Ban", interaction.user, member, reason, config.COLOR_ERROR)

    # ─── /unban ──────────────────────────────────────────────────────────────

    @app_commands.command(name="unban", description="Debanează un utilizator după ID")
    @app_commands.describe(user_id="ID-ul utilizatorului", reason="Motivul")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "Fără motiv"):
        try:
            user = await self.bot.fetch_user(int(user_id))
        except Exception:
            return await interaction.response.send_message(
                embed=error_embed("ID utilizator invalid."), ephemeral=True
            )
        try:
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(
                embed=success_embed(f"**{user}** a fost debanat.")
            )
        except discord.NotFound:
            await interaction.response.send_message(
                embed=error_embed("Utilizatorul nu este banat."), ephemeral=True
            )

    # ─── /kick ───────────────────────────────────────────────────────────────

    @app_commands.command(name="kick", description="Dă kick unui utilizator")
    @app_commands.describe(member="Utilizatorul", reason="Motivul")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Fără motiv"):
        if member.top_role >= interaction.user.top_role:
            return await interaction.response.send_message(
                embed=error_embed("Nu poți da kick unui utilizator cu rol mai mare sau egal cu al tău."),
                ephemeral=True
            )
        try:
            await member.send(embed=embed(
                title="👢 Ai primit kick",
                description=f"Ai primit kick de pe **{interaction.guild.name}**.\n**Motiv:** {reason}",
                color=config.COLOR_WARNING
            ))
        except Exception:
            pass
        await member.kick(reason=f"{interaction.user} | {reason}")
        await interaction.response.send_message(
            embed=success_embed(f"{member.mention} a primit kick.\n**Motiv:** {reason}")
        )
        await self.log_action(interaction.guild, "Kick", interaction.user, member, reason, config.COLOR_WARNING)

    # ─── /mute ───────────────────────────────────────────────────────────────

    @app_commands.command(name="mute", description="Mutează un utilizator (timeout)")
    @app_commands.describe(member="Utilizatorul", duration="Durata (ex: 10m, 1h, 1d)", reason="Motivul")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member,
                   duration: str = "10m", reason: str = "Fără motiv"):
        seconds = parse_time(duration)
        if seconds <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Format durată invalid. Exemplu: `10m`, `1h`, `2d`"), ephemeral=True
            )
        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=f"{interaction.user} | {reason}")
        await interaction.response.send_message(
            embed=success_embed(
                f"{member.mention} a fost mutat pentru **{format_duration(seconds)}**.\n**Motiv:** {reason}"
            )
        )
        await self.log_action(interaction.guild, "Mute", interaction.user, member, reason,
                               config.COLOR_WARNING, f"Durată: {format_duration(seconds)}")

    # ─── /unmute ─────────────────────────────────────────────────────────────

    @app_commands.command(name="unmute", description="Demutează un utilizator")
    @app_commands.describe(member="Utilizatorul")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        await member.timeout(None)
        await interaction.response.send_message(
            embed=success_embed(f"{member.mention} a fost demu­tat.")
        )

    # ─── /warn ───────────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Avertizează un utilizator")
    @app_commands.describe(member="Utilizatorul", reason="Motivul")
    @app_commands.checks.has_permissions(kick_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        warn_id = await db.add_warning(member.id, interaction.guild.id, interaction.user.id, reason, now_iso())
        warnings = await db.get_warnings(member.id, interaction.guild.id)
        try:
            await member.send(embed=embed(
                title="⚠️ Ai primit un avertisment",
                description=f"**Server:** {interaction.guild.name}\n**Motiv:** {reason}\n**Total avertismente:** {len(warnings)}",
                color=config.COLOR_WARNING
            ))
        except Exception:
            pass
        await interaction.response.send_message(
            embed=success_embed(
                f"{member.mention} a primit avertismentul **#{warn_id}**.\n"
                f"**Motiv:** {reason}\n**Total:** {len(warnings)} avertisment(e)"
            )
        )
        await self.log_action(interaction.guild, f"Warn #{warn_id}", interaction.user, member, reason, config.COLOR_WARNING)

    # ─── /warnings ───────────────────────────────────────────────────────────

    @app_commands.command(name="warnings", description="Afișează avertismentele unui utilizator")
    @app_commands.describe(member="Utilizatorul")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        warns = await db.get_warnings(target.id, interaction.guild.id)
        if not warns:
            return await interaction.response.send_message(
                embed=success_embed(f"{target.mention} nu are avertismente.")
            )
        desc = "\n".join(
            f"`#{w['id']}` — {w['reason']} *(de <@{w['mod_id']}>)*" for w in warns
        )
        e = embed(title=f"⚠️ Avertismente — {target.display_name}",
                  description=desc, color=config.COLOR_WARNING)
        e.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=e)

    # ─── /delwarn ────────────────────────────────────────────────────────────

    @app_commands.command(name="delwarn", description="Șterge un avertisment după ID")
    @app_commands.describe(warn_id="ID-ul avertismentului")
    @app_commands.checks.has_permissions(kick_members=True)
    async def delwarn(self, interaction: discord.Interaction, warn_id: int):
        deleted = await db.delete_warning(warn_id, interaction.guild.id)
        if deleted:
            await interaction.response.send_message(
                embed=success_embed(f"Avertismentul **#{warn_id}** a fost șters.")
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Avertismentul nu a fost găsit."), ephemeral=True
            )

    # ─── /clearwarns ─────────────────────────────────────────────────────────

    @app_commands.command(name="clearwarns", description="Șterge toate avertismentele unui utilizator")
    @app_commands.describe(member="Utilizatorul")
    @app_commands.checks.has_permissions(administrator=True)
    async def clearwarns(self, interaction: discord.Interaction, member: discord.Member):
        await db.clear_warnings(member.id, interaction.guild.id)
        await interaction.response.send_message(
            embed=success_embed(f"Toate avertismentele lui {member.mention} au fost șterse.")
        )

    # ─── /purge ──────────────────────────────────────────────────────────────

    @app_commands.command(name="purge", description="Șterge un număr de mesaje din canal")
    @app_commands.describe(amount="Numărul de mesaje (1-100)", member="Filtrează mesajele unui utilizator")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        if not 1 <= amount <= 100:
            return await interaction.response.send_message(
                embed=error_embed("Numărul trebuie să fie între 1 și 100."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        check = (lambda m: m.author == member) if member else None
        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(
            embed=success_embed(f"Au fost șterse **{len(deleted)}** mesaje."),
            ephemeral=True
        )

    # ─── /slowmode ────────────────────────────────────────────────────────────

    @app_commands.command(name="slowmode", description="Setează slowmode pe canal")
    @app_commands.describe(seconds="Secunde (0 = dezactivat, max 21600)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        await interaction.channel.edit(slowmode_delay=max(0, min(seconds, 21600)))
        if seconds == 0:
            await interaction.response.send_message(embed=success_embed("Slowmode dezactivat."))
        else:
            await interaction.response.send_message(
                embed=success_embed(f"Slowmode setat la **{seconds}s**.")
            )

    # ─── /lock / /unlock ──────────────────────────────────────────────────────

    @app_commands.command(name="lock", description="Blochează un canal")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(embed=success_embed("🔒 Canal blocat."))

    @app_commands.command(name="unlock", description="Deblochează un canal")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(embed=success_embed("🔓 Canal deblocat."))

    # ─── Task: auto check expired mutes ──────────────────────────────────────

    @tasks.loop(minutes=1)
    async def check_mutes(self):
        pass  # Discord handles timeout natively; placeholder for custom role-mutes if needed

    @check_mutes.before_loop
    async def before_check_mutes(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Moderation(bot))
