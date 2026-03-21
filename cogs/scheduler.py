import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta

import config
from utils import database as db
from utils.helpers import now_iso, parse_time, embed, success_embed, error_embed


class Scheduler(commands.Cog, name="Scheduler"):
    """Programare mesaje automate."""

    def __init__(self, bot):
        self.bot = bot
        self.check_scheduled.start()

    def cog_unload(self):
        self.check_scheduled.cancel()

    schedule_group = app_commands.Group(name="schedule", description="Programare mesaje")

    # ─── /schedule add ───────────────────────────────────────────────────────

    @schedule_group.command(name="add", description="Programează un mesaj să fie trimis")
    @app_commands.describe(
        channel="Canalul destinatar",
        time="Când să fie trimis (ex: 2h, 1d, sau dată: 2026-03-15 20:00)",
        message="Mesajul text (opțional dacă folosești embed)",
        embed_title="Titlu embed (opțional)",
        embed_desc="Descriere embed (opțional)",
        repeat="Repetare: none / daily / weekly"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def schedule_add(self, interaction: discord.Interaction,
                            channel: discord.TextChannel,
                            time: str,
                            message: str = None,
                            embed_title: str = None,
                            embed_desc: str = None,
                            repeat: str = "none"):
        if not message and not embed_title:
            return await interaction.response.send_message(
                embed=error_embed("Trebuie să specifici un mesaj sau un titlu de embed."), ephemeral=True
            )

        if repeat not in ("none", "daily", "weekly"):
            return await interaction.response.send_message(
                embed=error_embed("Repeat valid: `none`, `daily`, `weekly`"), ephemeral=True
            )

        # Parse time — try duration format first, then datetime string
        send_at = None
        from utils.helpers import parse_time as pt
        seconds = pt(time)
        if seconds >= 60:
            send_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        else:
            # Try datetime string "YYYY-MM-DD HH:MM"
            try:
                dt = datetime.strptime(time, "%Y-%m-%d %H:%M")
                dt = dt.replace(tzinfo=timezone.utc)
                if dt <= datetime.now(timezone.utc):
                    return await interaction.response.send_message(
                        embed=error_embed("Data specificată este în trecut."), ephemeral=True
                    )
                send_at = dt.isoformat()
            except ValueError:
                return await interaction.response.send_message(
                    embed=error_embed(
                        "Format timp invalid.\n"
                        "Folosește durate (ex: `2h`, `1d`) sau date (ex: `2026-03-15 20:00`)."
                    ),
                    ephemeral=True
                )

        repeat_val = None if repeat == "none" else repeat
        msg_id = await db.create_scheduled_message(
            interaction.guild.id, channel.id,
            message, embed_title, embed_desc, None,
            send_at, interaction.user.id, repeat_val
        )

        send_ts = int(datetime.fromisoformat(send_at).timestamp())
        await interaction.response.send_message(embed=embed(
            title="📅 Mesaj programat!",
            description=(
                f"**ID:** `#{msg_id}`\n"
                f"**Canal:** {channel.mention}\n"
                f"**Când:** <t:{send_ts}:F> (<t:{send_ts}:R>)\n"
                f"**Repetare:** {repeat}\n"
                f"**Mesaj:** {(message or embed_title or '')[:100]}"
            ),
            color=config.COLOR_INFO
        ), ephemeral=True)

    # ─── /schedule list ──────────────────────────────────────────────────────

    @schedule_group.command(name="list", description="Afișează mesajele programate")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def schedule_list(self, interaction: discord.Interaction):
        messages = await db.get_guild_scheduled_messages(interaction.guild.id)
        if not messages:
            return await interaction.response.send_message(
                embed=embed(title="📅 Mesaje programate", description="Nu există mesaje programate.",
                            color=config.COLOR_INFO),
                ephemeral=True
            )
        lines = []
        for m in messages:
            ch = interaction.guild.get_channel(m["channel_id"])
            ch_str = ch.mention if ch else "canal şters"
            send_at = datetime.fromisoformat(m["send_at"])
            if send_at.tzinfo is None:
                send_at = send_at.replace(tzinfo=timezone.utc)
            ts = int(send_at.timestamp())
            preview = m.get("content") or m.get("embed_title") or "embed"
            repeat = f" 🔄 {m['repeat']}" if m.get("repeat") else ""
            lines.append(f"`#{m['id']}` {ch_str} — <t:{ts}:R>{repeat}\n　└ _{preview[:60]}_")

        await interaction.response.send_message(embed=embed(
            title=f"📅 Mesaje programate — {len(messages)}",
            description="\n".join(lines),
            color=config.COLOR_INFO
        ), ephemeral=True)

    # ─── /schedule delete ────────────────────────────────────────────────────

    @schedule_group.command(name="delete", description="Şterge un mesaj programat după ID")
    @app_commands.describe(message_id="ID-ul mesajului programat")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def schedule_delete(self, interaction: discord.Interaction, message_id: int):
        deleted = await db.delete_scheduled_message(message_id, interaction.guild.id)
        if deleted:
            await interaction.response.send_message(
                embed=success_embed(f"Mesajul programat **#{message_id}** şters."), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=error_embed(f"Mesajul **#{message_id}** nu a fost găsit."), ephemeral=True
            )

    # ─── Background task ─────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def check_scheduled(self):
        now = datetime.now(timezone.utc)
        due = await db.get_due_scheduled_messages(now.isoformat())
        for msg in due:
            guild = self.bot.get_guild(msg["guild_id"])
            if not guild:
                await db.mark_scheduled_sent(msg["id"])
                continue

            channel = guild.get_channel(msg["channel_id"])
            if not channel:
                await db.mark_scheduled_sent(msg["id"])
                continue

            # Build content
            content = msg.get("content")
            send_embed = None
            if msg.get("embed_title") or msg.get("embed_desc"):
                color = int(msg["embed_color"].lstrip("#"), 16) if msg.get("embed_color") else config.COLOR_PRIMARY
                send_embed = embed(
                    title=msg.get("embed_title"),
                    description=msg.get("embed_desc"),
                    color=color
                )

            try:
                await channel.send(content=content, embed=send_embed)
            except Exception:
                pass

            # Handle repeat
            if msg.get("repeat") == "daily":
                next_send = (datetime.fromisoformat(msg["send_at"]).replace(tzinfo=timezone.utc) + timedelta(days=1)).isoformat()
                await db.mark_scheduled_sent(msg["id"], next_send)
            elif msg.get("repeat") == "weekly":
                next_send = (datetime.fromisoformat(msg["send_at"]).replace(tzinfo=timezone.utc) + timedelta(weeks=1)).isoformat()
                await db.mark_scheduled_sent(msg["id"], next_send)
            else:
                await db.mark_scheduled_sent(msg["id"])

    @check_scheduled.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Scheduler(bot))
