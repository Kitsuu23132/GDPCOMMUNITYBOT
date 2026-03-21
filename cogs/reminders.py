import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta

import config
from utils import database as db
from utils.helpers import now_iso, parse_time, format_duration, embed, success_embed, error_embed


class Reminders(commands.Cog, name="Reminder"):
    """Sistem de remindere personale."""

    def __init__(self, bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    reminder_group = app_commands.Group(name="reminder", description="Sistem de remindere")

    # ─── /reminder add ───────────────────────────────────────────────────────

    @reminder_group.command(name="add", description="Setează un reminder")
    @app_commands.describe(time="Durata (ex: 30m, 2h, 1d)", message="Mesajul reminderului")
    async def remind(self, interaction: discord.Interaction, time: str, message: str):
        seconds = parse_time(time)
        if seconds < 60:
            return await interaction.response.send_message(
                embed=error_embed("Durata minimă este 1 minut. Ex: `5m`, `2h`, `1d`"), ephemeral=True
            )
        if seconds > 30 * 86400:
            return await interaction.response.send_message(
                embed=error_embed("Durata maximă este 30 de zile."), ephemeral=True
            )
        remind_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        reminder_id = await db.create_reminder(
            interaction.user.id, interaction.guild.id,
            interaction.channel.id, message, remind_at, now_iso()
        )
        ts = int((datetime.now(timezone.utc) + timedelta(seconds=seconds)).timestamp())
        await interaction.response.send_message(embed=embed(
            title="⏰ Reminder setat!",
            description=f"**Mesaj:** {message}\n**Când:** <t:{ts}:R>\n**ID:** `#{reminder_id}`",
            color=config.COLOR_INFO
        ))

    # ─── /reminder list ──────────────────────────────────────────────────────

    @reminder_group.command(name="list", description="Afișează reminderele tale active")
    async def reminders_list(self, interaction: discord.Interaction):
        reminders = await db.get_user_reminders(interaction.user.id)
        if not reminders:
            return await interaction.response.send_message(
                embed=embed(title="⏰ Remindere", description="Nu ai remindere active.", color=config.COLOR_INFO),
                ephemeral=True
            )
        lines = []
        for r in reminders:
            remind_at = datetime.fromisoformat(r["remind_at"])
            if remind_at.tzinfo is None:
                remind_at = remind_at.replace(tzinfo=timezone.utc)
            ts = int(remind_at.timestamp())
            lines.append(f"`#{r['id']}` — <t:{ts}:R>\n　└ _{r['content'][:80]}_")
        await interaction.response.send_message(embed=embed(
            title=f"⏰ Remindere — {len(reminders)} active",
            description="\n".join(lines),
            color=config.COLOR_INFO
        ), ephemeral=True)

    # ─── /reminder cancel ────────────────────────────────────────────────────

    @reminder_group.command(name="cancel", description="Anulează un reminder după ID")
    @app_commands.describe(reminder_id="ID-ul reminderului")
    async def cancel_reminder(self, interaction: discord.Interaction, reminder_id: int):
        deleted = await db.delete_reminder(reminder_id, interaction.user.id)
        if deleted:
            await interaction.response.send_message(
                embed=success_embed(f"Reminder **#{reminder_id}** anulat."), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=error_embed("Reminder-ul nu a fost găsit sau nu îți aparține."), ephemeral=True
            )

    # ─── Background task ─────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        now = datetime.now(timezone.utc).isoformat()
        due = await db.get_due_reminders(now)
        for r in due:
            await db.mark_reminder_done(r["id"])
            user = self.bot.get_user(r["user_id"])
            if not user:
                try:
                    user = await self.bot.fetch_user(r["user_id"])
                except Exception:
                    continue

            e = embed(
                title="⏰ Reminder!",
                description=r["content"],
                color=config.COLOR_INFO,
                fields=[("Setat", f"<t:{int(datetime.fromisoformat(r['created_at']).replace(tzinfo=timezone.utc).timestamp())}:R>", True)]
            )

            # Try channel first, then DM
            guild = self.bot.get_guild(r["guild_id"])
            ch = guild.get_channel(r["channel_id"]) if guild else None
            sent = False
            if ch:
                try:
                    await ch.send(content=user.mention, embed=e)
                    sent = True
                except Exception:
                    pass
            if not sent:
                try:
                    await user.send(embed=e)
                except Exception:
                    pass

    @check_reminders.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Reminders(bot))
