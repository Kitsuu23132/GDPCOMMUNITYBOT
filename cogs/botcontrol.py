import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import sys
import os
import asyncio

import config
from utils.helpers import embed, success_embed, error_embed, warning_embed


class BotControl(commands.Cog, name="BotControl"):
    """Comenzi de control al botului: stop, restart, freeze, unfreeze."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Ensure _frozen flag exists on bot
        if not hasattr(bot, "_frozen"):
            bot._frozen = False
        if not hasattr(bot, "_frozen_reason"):
            bot._frozen_reason = ""
        if not hasattr(bot, "_frozen_since"):
            bot._frozen_since = None

    # ─── Interaction guard (freeze) ──────────────────────────────────────────

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global check injected into the bot's tree — blocks all interactions when frozen."""
        if not self.bot._frozen:
            return True
        # Allow only admins to use unfreeze when frozen
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message(
            embed=embed(
                title="🧊 Bot Înghețat",
                description=(
                    f"Botul este momentan în **modul de mentenanță**.\n"
                    f"**Motiv:** {self.bot._frozen_reason or 'Mentenanță'}\n"
                    f"Revino mai târziu! 🔧"
                ),
                color=0x00B0F4
            ),
            ephemeral=True
        )
        return False

    # ─── Group ───────────────────────────────────────────────────────────────

    bc_group = app_commands.Group(name="botcontrol", description="Control și administrare bot")

    # ─── /botcontrol status ──────────────────────────────────────────────────

    @bc_group.command(name="invite", description="Link pentru a adăuga acest bot pe un server")
    @app_commands.checks.has_permissions(administrator=True)
    async def bc_invite(self, interaction: discord.Interaction):
        if not self.bot.user:
            return await interaction.response.send_message(
                embed=error_embed("Botul nu e încărcat."), ephemeral=True
            )
        app = await self.bot.application_info()
        client_id = app.id
        url = (
            f"https://discord.com/api/oauth2/authorize"
            f"?client_id={client_id}"
            f"&permissions=8"
            f"&scope=bot%20applications.commands"
        )
        await interaction.response.send_message(embed=embed(
            title="🔗 Link invite — acest bot",
            description=(
                f"**Application ID:** `{client_id}`\n\n"
                f"Folosește acest link ca să adaugi **acest** bot (nu vechiul):\n{url}\n\n"
                f"Dacă vechiul bot e încă pe server, dă-i **Kick** din Server Settings → Integrations, "
                f"apoi adaugă din nou doar cu linkul de mai sus."
            ),
            color=config.COLOR_PRIMARY
        ), ephemeral=True)

    @bc_group.command(name="status", description="Afișează statusul botului")
    @app_commands.checks.has_permissions(administrator=True)
    async def bc_status(self, interaction: discord.Interaction):
        import time
        uptime_secs = int(time.time() - getattr(self.bot, "_start_time", time.time()))
        h, rem = divmod(uptime_secs, 3600)
        m, s = divmod(rem, 60)
        frozen = self.bot._frozen
        since_str = ""
        if frozen and self.bot._frozen_since:
            since_str = f"\n**Înghețat de la:** <t:{int(self.bot._frozen_since.timestamp())}:R>"

        e = embed(
            title="🤖 Status Bot",
            color=0x00B0F4 if frozen else config.COLOR_SUCCESS,
            fields=[
                ("⚡ Stare", "🧊 **ÎNGHEȚAT**" if frozen else "✅ **ACTIV**", True),
                ("⏱️ Uptime", f"{h}h {m}m {s}s", True),
                ("🏓 Latență", f"{round(self.bot.latency * 1000)}ms", True),
                ("📦 Cog-uri", str(len(self.bot.cogs)), True),
                ("📋 Comenzi", str(len(self.bot.tree.get_commands())), True),
                ("👥 Servere", str(len(self.bot.guilds)), True),
            ]
        )
        if frozen:
            e.add_field(
                name="🔒 Motiv înghețare",
                value=self.bot._frozen_reason or "Mentenanță",
                inline=False
            )
            e.description = since_str
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ─── /botcontrol freeze ──────────────────────────────────────────────────

    @bc_group.command(name="freeze", description="Îngheață botul — blochează toate comenzile")
    @app_commands.describe(reason="Motivul (afișat utilizatorilor)")
    @app_commands.checks.has_permissions(administrator=True)
    async def bc_freeze(self, interaction: discord.Interaction, reason: str = "Mentenanță"):
        if self.bot._frozen:
            return await interaction.response.send_message(
                embed=warning_embed("Botul este deja înghețat!"), ephemeral=True
            )
        self.bot._frozen = True
        self.bot._frozen_reason = reason
        self.bot._frozen_since = datetime.now(timezone.utc)

        await interaction.response.send_message(embed=embed(
            title="🧊 Bot Înghețat",
            description=(
                f"Toate comenzile și interacțiunile au fost **blocate**.\n"
                f"**Motiv:** {reason}\n\n"
                f"Utilizatorii vor vedea un mesaj de mentenanță.\n"
                f"Folosește `/botcontrol unfreeze` pentru a reactiva."
            ),
            color=0x00B0F4
        ))

        # Update presence
        await self.bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="🔧 Mentenanță..."
            )
        )

    # ─── /botcontrol unfreeze ────────────────────────────────────────────────

    @bc_group.command(name="unfreeze", description="Dezgheață botul — reactivează toate comenzile")
    @app_commands.checks.has_permissions(administrator=True)
    async def bc_unfreeze(self, interaction: discord.Interaction):
        if not self.bot._frozen:
            return await interaction.response.send_message(
                embed=warning_embed("Botul nu este înghețat!"), ephemeral=True
            )
        duration = ""
        if self.bot._frozen_since:
            diff = datetime.now(timezone.utc) - self.bot._frozen_since
            m, s = divmod(int(diff.total_seconds()), 60)
            h, m = divmod(m, 60)
            duration = f"\n**Timp mentenanță:** {h}h {m}m {s}s"

        self.bot._frozen = False
        self.bot._frozen_reason = ""
        self.bot._frozen_since = None

        await interaction.response.send_message(embed=embed(
            title="✅ Bot Dezghețat",
            description=f"Toate comenzile și interacțiunile sunt **active** din nou!{duration}",
            color=config.COLOR_SUCCESS
        ))

        # Restore presence
        await self.bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{config.PREFIX}help | GDP Community"
            )
        )

    # ─── /botcontrol restart ─────────────────────────────────────────────────

    @bc_group.command(name="restart", description="Repornește botul")
    @app_commands.checks.has_permissions(administrator=True)
    async def bc_restart(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=embed(
            title="🔄 Repornire...",
            description="Botul se repornește. Va reveni online în câteva secunde! ⏳",
            color=config.COLOR_WARNING
        ))

        # Update presence before restart
        await self.bot.change_presence(
            status=discord.Status.idle,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="🔄 Se repornește..."
            )
        )

        await asyncio.sleep(1)
        # Close bot cleanly then re-exec the same script
        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ─── /botcontrol stop ────────────────────────────────────────────────────

    @bc_group.command(name="stop", description="Oprește botul complet")
    @app_commands.checks.has_permissions(administrator=True)
    async def bc_stop(self, interaction: discord.Interaction):
        confirm_view = StopConfirmView()
        await interaction.response.send_message(
            embed=embed(
                title="⛔ Confirmare oprire",
                description=(
                    "Ești sigur că vrei să **oprești** botul?\n"
                    "Acesta va deveni **offline** până când îl repornești manual.\n\n"
                    "Apasă **Confirmă** pentru a opri sau **Anulează**."
                ),
                color=config.COLOR_ERROR
            ),
            view=confirm_view,
            ephemeral=True
        )


class StopConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="Confirmă oprirea", style=discord.ButtonStyle.danger, emoji="⛔")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=embed(
                title="⛔ Bot oprit",
                description="Botul se opreşte. La revedere! 👋",
                color=config.COLOR_ERROR
            ),
            view=None
        )
        await asyncio.sleep(1)
        await interaction.client.close()

    @discord.ui.button(label="Anulează", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            embed=success_embed("Oprire anulată. Botul continuă normal."),
            view=None
        )


async def setup(bot: commands.Bot):
    cog = BotControl(bot)
    await bot.add_cog(cog)
    # Inject the freeze check into the command tree
    bot.tree.interaction_check = cog.interaction_check
