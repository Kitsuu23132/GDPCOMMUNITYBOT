<<<<<<< HEAD
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed, warning_embed


# ─── Status config ────────────────────────────────────────────────────────────

STATUS_CONFIG = {
    "pending":     ("🟡", "În așteptare",  0xFEE75C),
    "reviewing":   ("🔵", "În curs",       0x00B0F4),
    "accepted":    ("🟢", "Acceptat",      0x57F287),
    "dismissed":   ("🔴", "Respins",       0xED4245),
    "banned":      ("⛔", "Ban aplicat",   0xED4245),
}


# ─── Report Modal ─────────────────────────────────────────────────────────────

class ReportModal(discord.ui.Modal, title="📋 Raportare Jucător"):
    reported_user = discord.ui.TextInput(
        label="Utilizatorul raportat (username sau ID)",
        placeholder="Ex: Ionescu#1234 sau 123456789012345678",
        max_length=100,
        required=True
    )
    reason = discord.ui.TextInput(
        label="Motivul raportului",
        placeholder="Descrie pe scurt ce a făcut utilizatorul...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    evidence = discord.ui.TextInput(
        label="Dovezi (opțional)",
        placeholder="Link screenshot, clip video, sau descriere detaliată...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Resolve reported user
        reported_input = self.reported_user.value.strip()
        reported_member = None

        # Try by ID
        try:
            uid = int(reported_input)
            reported_member = interaction.guild.get_member(uid)
            if not reported_member:
                reported_member = await interaction.guild.fetch_member(uid)
        except (ValueError, discord.NotFound):
            pass

        # Try by name
        if not reported_member:
            name_lower = reported_input.lower().replace("#", "").split("#")[0]
            reported_member = discord.utils.find(
                lambda m: m.name.lower() == name_lower or m.display_name.lower() == name_lower,
                interaction.guild.members
            )

        if not reported_member:
            return await interaction.followup.send(
                embed=error_embed(
                    f"Utilizatorul **{reported_input}** nu a fost găsit pe server.\n"
                    "Verifică username-ul sau folosește ID-ul Discord."
                ),
                ephemeral=True
            )

        if reported_member == interaction.user:
            return await interaction.followup.send(
                embed=error_embed("Nu te poți raporta pe tine însuți."),
                ephemeral=True
            )

        if reported_member.bot:
            return await interaction.followup.send(
                embed=error_embed("Nu poți raporta un bot."),
                ephemeral=True
            )

        reason_text = self.reason.value.strip()
        evidence_text = self.evidence.value.strip() if self.evidence.value else "Fără dovezi"

        # Save to DB
        report_id = await db.create_report(
            interaction.guild.id,
            interaction.user.id,
            reported_member.id,
            reason_text,
            evidence_text,
            now_iso()
        )

        # Get report channel
        settings = await db.get_guild_settings(interaction.guild.id)
        report_ch_id = settings.get("report_channel") or 0

        if not report_ch_id:
            await interaction.followup.send(
                embed=warning_embed(
                    f"Raportul tău **#{report_id}** a fost înregistrat, dar nu există un canal de rapoarte configurat.\n"
                    "Un administrator trebuie să ruleze `/setreportchannel`."
                ),
                ephemeral=True
            )
            return

        report_ch = interaction.guild.get_channel(report_ch_id)
        if not report_ch:
            return await interaction.followup.send(
                embed=error_embed("Canalul de rapoarte nu mai există. Contactează un administrator."),
                ephemeral=True
            )

        # Build report embed
        report_embed = build_report_embed(
            report_id, interaction.user, reported_member,
            reason_text, evidence_text, "pending"
        )

        view = ReportActionView(report_id)
        msg = await report_ch.send(embed=report_embed, view=view)
        await db.set_report_message(report_id, msg.id, report_ch.id)

        await interaction.followup.send(
            embed=success_embed(
                f"✅ Raportul tău **#{report_id}** a fost trimis staff-ului!\n"
                f"**Utilizator raportat:** {reported_member.mention}\n"
                f"Vei fi notificat când staff-ul îl procesează."
            ),
            ephemeral=True
        )


# ─── Report embed builder ─────────────────────────────────────────────────────

def build_report_embed(report_id: int, reporter: discord.Member, reported: discord.Member,
                        reason: str, evidence: str, status: str,
                        handler: discord.Member = None) -> discord.Embed:
    status_emoji, status_label, status_color = STATUS_CONFIG.get(status, ("🟡", "În așteptare", 0xFEE75C))

    e = discord.Embed(
        title=f"📋 Raport #{report_id}",
        color=status_color,
        timestamp=datetime.now(timezone.utc)
    )
    e.add_field(name="🎯 Utilizator raportat",
                value=f"{reported.mention}\n`{reported}` • ID: `{reported.id}`", inline=True)
    e.add_field(name="📣 Raportat de",
                value=f"{reporter.mention}\n`{reporter}`", inline=True)
    e.add_field(name="⚡ Status",
                value=f"{status_emoji} **{status_label}**", inline=True)
    e.add_field(name="📝 Motiv",
                value=f"```{reason}```", inline=False)
    e.add_field(name="🔍 Dovezi",
                value=evidence if evidence and evidence != "Fără dovezi" else "*Nu au fost furnizate dovezi*",
                inline=False)

    if handler:
        e.add_field(name="👮 Procesat de", value=handler.mention, inline=True)

    e.set_thumbnail(url=reported.display_avatar.url)
    e.set_footer(text=f"GDP Community • Report #{report_id}")
    return e


# ─── Action buttons view ─────────────────────────────────────────────────────

class ReportActionView(discord.ui.View):
    def __init__(self, report_id: int):
        super().__init__(timeout=None)
        self.report_id = report_id

    @discord.ui.button(label="În curs", style=discord.ButtonStyle.primary,
                       emoji="🔵", custom_id="report_reviewing")
    async def reviewing_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_status(interaction, "reviewing")

    @discord.ui.button(label="Acceptat — Warn", style=discord.ButtonStyle.success,
                       emoji="⚠️", custom_id="report_accept_warn")
    async def accept_warn_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, "accepted", warn=True)

    @discord.ui.button(label="Acceptat — Ban", style=discord.ButtonStyle.danger,
                       emoji="🔨", custom_id="report_accept_ban")
    async def accept_ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, "banned", ban=True)

    @discord.ui.button(label="Respins", style=discord.ButtonStyle.secondary,
                       emoji="❌", custom_id="report_dismiss")
    async def dismiss_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, "dismissed")

    async def _get_report_and_check_perms(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message(
                embed=error_embed("Doar staff-ul poate procesa rapoarte."), ephemeral=True
            )
            return None
        report = await db.get_report(self.report_id)
        if not report:
            await interaction.response.send_message(
                embed=error_embed("Raportul nu mai există în baza de date."), ephemeral=True
            )
            return None
        return report

    async def _update_status(self, interaction: discord.Interaction, status: str):
        report = await self._get_report_and_check_perms(interaction)
        if not report:
            return

        await db.update_report(self.report_id, status, interaction.user.id, now_iso())

        reporter = interaction.guild.get_member(report["reporter_id"])
        reported = interaction.guild.get_member(report["reported_id"])

        if reporter and reported:
            new_embed = build_report_embed(
                self.report_id, reporter, reported,
                report["reason"], report["evidence"], status, interaction.user
            )
            await interaction.message.edit(embed=new_embed, view=self)

        await interaction.response.send_message(
            embed=success_embed(f"Raportul **#{self.report_id}** marcat ca **În curs** de tine."),
            ephemeral=True
        )

    async def _handle_action(self, interaction: discord.Interaction, status: str,
                              warn: bool = False, ban: bool = False):
        report = await self._get_report_and_check_perms(interaction)
        if not report:
            return

        await interaction.response.defer()

        reporter = interaction.guild.get_member(report["reporter_id"])
        reported = interaction.guild.get_member(report["reported_id"])

        # Apply moderation action
        action_result = ""
        if reported:
            if warn:
                warn_id = await db.add_warning(
                    reported.id, interaction.guild.id, interaction.user.id,
                    f"Raport #{self.report_id}: {report['reason']}", now_iso()
                )
                action_result = f"⚠️ Avertisment #{warn_id} aplicat lui {reported.mention}"
                try:
                    await reported.send(embed=embed(
                        title="⚠️ Ai primit un avertisment",
                        description=(
                            f"**Server:** {interaction.guild.name}\n"
                            f"**Motiv:** Raport #{self.report_id} — {report['reason']}\n"
                            f"**Aplicat de:** Staff"
                        ),
                        color=config.COLOR_WARNING
                    ))
                except discord.Forbidden:
                    pass

            elif ban:
                try:
                    await reported.send(embed=embed(
                        title="🔨 Ai fost banat",
                        description=(
                            f"Ai fost banat de pe **{interaction.guild.name}**.\n"
                            f"**Motiv:** Raport #{self.report_id} — {report['reason']}"
                        ),
                        color=config.COLOR_ERROR
                    ))
                except discord.Forbidden:
                    pass
                try:
                    await reported.ban(
                        reason=f"Raport #{self.report_id} procesat de {interaction.user} | {report['reason']}"
                    )
                    action_result = f"🔨 **{reported}** a fost banat"
                except discord.Forbidden:
                    action_result = "❌ Nu am putut da ban (permisiuni insuficiente)"

        # Update DB
        await db.update_report(self.report_id, status, interaction.user.id, now_iso())

        # Update embed & disable buttons
        if reporter and reported:
            new_embed = build_report_embed(
                self.report_id, reporter, reported,
                report["reason"], report["evidence"], status, interaction.user
            )
            closed_view = discord.ui.View()
            await interaction.message.edit(embed=new_embed, view=closed_view)

        status_emoji, status_label, _ = STATUS_CONFIG.get(status, ("🟡", "?", 0))

        # Notify reporter
        if reporter:
            try:
                notify_desc = (
                    f"Raportul tău **#{self.report_id}** împotriva lui "
                    f"**{reported or report['reported_id']}** a fost procesat.\n"
                    f"**Status:** {status_emoji} {status_label}\n"
                    f"**Procesat de:** Staff"
                )
                if action_result:
                    notify_desc += f"\n**Acțiune aplicată:** {action_result}"
                await reporter.send(embed=embed(
                    title="📋 Raportul tău a fost procesat!",
                    description=notify_desc,
                    color=STATUS_CONFIG[status][2]
                ))
            except discord.Forbidden:
                pass

        result_msg = f"Raportul **#{self.report_id}** marcat ca **{status_label}**."
        if action_result:
            result_msg += f"\n{action_result}"
        await interaction.followup.send(embed=success_embed(result_msg), ephemeral=True)


# ─── Panel button ─────────────────────────────────────────────────────────────

class ReportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Raportează un jucător",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="open_report_modal"
    )
    async def report_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Reports(commands.Cog, name="Rapoarte"):
    """Sistem de raportare a jucătorilor."""

    def __init__(self, bot):
        self.bot = bot
        bot.add_view(ReportPanelView())

    @app_commands.command(name="reportpanel", description="[Admin] Creează panoul de raportare în canal")
    @app_commands.checks.has_permissions(administrator=True)
    async def report_panel(self, interaction: discord.Interaction):
        e = embed(
            title="🚨 Raportare Jucător — GDP Community",
            description=(
                "Ai întâlnit un comportament toxic, cheating sau o încălcare a regulilor?\n\n"
                "**Apasă butonul de mai jos** pentru a trimite un raport staff-ului.\n\n"
                "**📌 Reguli pentru rapoarte:**\n"
                "• Furnizează dovezi clare (screenshot, clip, ID mesaj)\n"
                "• Descrie situația cât mai detaliat posibil\n"
                "• Rapoartele false vor fi sancționate\n"
                "• Raportul tău este confidențial — doar staff-ul îl vede\n\n"
                "**⏱️ Timp de răspuns:** Staff-ul va procesa raportul în cel mai scurt timp."
            ),
            color=config.COLOR_ERROR,
            thumbnail=interaction.guild.icon.url if interaction.guild.icon else None
        )
        e.set_footer(text="GDP Community • Sistem de Raportare")
        await interaction.channel.send(embed=e, view=ReportPanelView())
        await interaction.response.send_message(
            embed=success_embed("Panoul de raportare a fost creat!"), ephemeral=True
        )

    @app_commands.command(name="setreportchannel", description="[Admin] Setează canalul unde vin rapoartele")
    @app_commands.describe(channel="Canalul privat pentru staff")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_report_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "report_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Rapoartele vor fi trimise în {channel.mention}.")
        )

    @app_commands.command(name="reports", description="[Staff] Afișează rapoartele recente")
    @app_commands.describe(
        status="Filtrează după status (pending/reviewing/accepted/dismissed/banned)",
        member="Filtrează rapoartele despre un utilizator specific"
    )
    @app_commands.checks.has_permissions(kick_members=True)
    async def list_reports(self, interaction: discord.Interaction,
                            status: str = None, member: discord.Member = None):
        await interaction.response.defer(ephemeral=True)

        if member:
            reports = await db.get_reports_against(member.id, interaction.guild.id)
            title = f"📋 Rapoarte despre {member.display_name}"
        else:
            reports = await db.get_all_reports(interaction.guild.id, status)
            title = f"📋 Rapoarte recente{' — ' + status if status else ''}"

        if not reports:
            return await interaction.followup.send(
                embed=embed(title=title, description="Nu există rapoarte.", color=config.COLOR_WARNING),
                ephemeral=True
            )

        lines = []
        for r in reports[:15]:
            reporter = interaction.guild.get_member(r["reporter_id"])
            reported = interaction.guild.get_member(r["reported_id"])
            s_emoji, s_label, _ = STATUS_CONFIG.get(r["status"], ("🟡", r["status"], 0))
            reporter_name = reporter.display_name if reporter else f"ID:{r['reporter_id']}"
            reported_name = reported.display_name if reported else f"ID:{r['reported_id']}"
            lines.append(
                f"{s_emoji} **#{r['id']}** — {reported_name} (raportat de {reporter_name})\n"
                f"　└ _{r['reason'][:60]}{'...' if len(r['reason']) > 60 else ''}_"
            )

        e = embed(title=title, description="\n".join(lines), color=config.COLOR_ERROR)
        e.set_footer(text=f"Total: {len(reports)} raport(e)")
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="reportinfo", description="[Staff] Afișează detaliile unui raport")
    @app_commands.describe(report_id="ID-ul raportului")
    @app_commands.checks.has_permissions(kick_members=True)
    async def report_info(self, interaction: discord.Interaction, report_id: int):
        report = await db.get_report(report_id)
        if not report or report["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message(
                embed=error_embed(f"Raportul **#{report_id}** nu a fost găsit."), ephemeral=True
            )
        reporter = interaction.guild.get_member(report["reporter_id"])
        reported = interaction.guild.get_member(report["reported_id"])
        handler = interaction.guild.get_member(report["handled_by"]) if report.get("handled_by") else None

        e = build_report_embed(
            report_id,
            reporter or interaction.user,
            reported or interaction.user,
            report["reason"],
            report["evidence"] or "Fără dovezi",
            report["status"],
            handler
        )
        if report.get("channel_id") and report.get("message_id"):
            e.add_field(
                name="🔗 Link mesaj",
                value=f"[Sari la raport](https://discord.com/channels/{interaction.guild.id}/{report['channel_id']}/{report['message_id']})",
                inline=True
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="report", description="Raportează un jucător direct prin comandă")
    @app_commands.describe(
        member="Utilizatorul pe care vrei să-l raportezi",
        reason="Motivul raportului",
        evidence="Dovezi (link sau descriere)"
    )
    async def report_cmd(self, interaction: discord.Interaction,
                          member: discord.Member, reason: str, evidence: str = "Fără dovezi"):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("Nu te poți raporta pe tine însuți."), ephemeral=True
            )
        if member.bot:
            return await interaction.response.send_message(
                embed=error_embed("Nu poți raporta un bot."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        report_id = await db.create_report(
            interaction.guild.id, interaction.user.id, member.id,
            reason, evidence, now_iso()
        )

        settings = await db.get_guild_settings(interaction.guild.id)
        report_ch_id = settings.get("report_channel") or 0

        if not report_ch_id:
            return await interaction.followup.send(
                embed=warning_embed(
                    f"Raportul **#{report_id}** înregistrat, dar nu există canal de rapoarte configurat.\n"
                    "Contactează un administrator."
                ),
                ephemeral=True
            )

        report_ch = interaction.guild.get_channel(report_ch_id)
        if not report_ch:
            return await interaction.followup.send(
                embed=error_embed("Canalul de rapoarte nu mai există."), ephemeral=True
            )

        report_embed = build_report_embed(
            report_id, interaction.user, member, reason, evidence, "pending"
        )
        view = ReportActionView(report_id)
        msg = await report_ch.send(embed=report_embed, view=view)
        await db.set_report_message(report_id, msg.id, report_ch.id)

        await interaction.followup.send(
            embed=success_embed(
                f"✅ Raportul **#{report_id}** a fost trimis staff-ului!\n"
                f"**Utilizator raportat:** {member.mention}"
            ),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Reports(bot))
=======
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed, warning_embed


# ─── Status config ────────────────────────────────────────────────────────────

STATUS_CONFIG = {
    "pending":     ("🟡", "În așteptare",  0xFEE75C),
    "reviewing":   ("🔵", "În curs",       0x00B0F4),
    "accepted":    ("🟢", "Acceptat",      0x57F287),
    "dismissed":   ("🔴", "Respins",       0xED4245),
    "banned":      ("⛔", "Ban aplicat",   0xED4245),
}


# ─── Report Modal ─────────────────────────────────────────────────────────────

class ReportModal(discord.ui.Modal, title="📋 Raportare Jucător"):
    reported_user = discord.ui.TextInput(
        label="Utilizatorul raportat (username sau ID)",
        placeholder="Ex: Ionescu#1234 sau 123456789012345678",
        max_length=100,
        required=True
    )
    reason = discord.ui.TextInput(
        label="Motivul raportului",
        placeholder="Descrie pe scurt ce a făcut utilizatorul...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True
    )
    evidence = discord.ui.TextInput(
        label="Dovezi (opțional)",
        placeholder="Link screenshot, clip video, sau descriere detaliată...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Resolve reported user
        reported_input = self.reported_user.value.strip()
        reported_member = None

        # Try by ID
        try:
            uid = int(reported_input)
            reported_member = interaction.guild.get_member(uid)
            if not reported_member:
                reported_member = await interaction.guild.fetch_member(uid)
        except (ValueError, discord.NotFound):
            pass

        # Try by name
        if not reported_member:
            name_lower = reported_input.lower().replace("#", "").split("#")[0]
            reported_member = discord.utils.find(
                lambda m: m.name.lower() == name_lower or m.display_name.lower() == name_lower,
                interaction.guild.members
            )

        if not reported_member:
            return await interaction.followup.send(
                embed=error_embed(
                    f"Utilizatorul **{reported_input}** nu a fost găsit pe server.\n"
                    "Verifică username-ul sau folosește ID-ul Discord."
                ),
                ephemeral=True
            )

        if reported_member == interaction.user:
            return await interaction.followup.send(
                embed=error_embed("Nu te poți raporta pe tine însuți."),
                ephemeral=True
            )

        if reported_member.bot:
            return await interaction.followup.send(
                embed=error_embed("Nu poți raporta un bot."),
                ephemeral=True
            )

        reason_text = self.reason.value.strip()
        evidence_text = self.evidence.value.strip() if self.evidence.value else "Fără dovezi"

        # Save to DB
        report_id = await db.create_report(
            interaction.guild.id,
            interaction.user.id,
            reported_member.id,
            reason_text,
            evidence_text,
            now_iso()
        )

        # Get report channel
        settings = await db.get_guild_settings(interaction.guild.id)
        report_ch_id = settings.get("report_channel") or 0

        if not report_ch_id:
            await interaction.followup.send(
                embed=warning_embed(
                    f"Raportul tău **#{report_id}** a fost înregistrat, dar nu există un canal de rapoarte configurat.\n"
                    "Un administrator trebuie să ruleze `/setreportchannel`."
                ),
                ephemeral=True
            )
            return

        report_ch = interaction.guild.get_channel(report_ch_id)
        if not report_ch:
            return await interaction.followup.send(
                embed=error_embed("Canalul de rapoarte nu mai există. Contactează un administrator."),
                ephemeral=True
            )

        # Build report embed
        report_embed = build_report_embed(
            report_id, interaction.user, reported_member,
            reason_text, evidence_text, "pending"
        )

        view = ReportActionView(report_id)
        msg = await report_ch.send(embed=report_embed, view=view)
        await db.set_report_message(report_id, msg.id, report_ch.id)

        await interaction.followup.send(
            embed=success_embed(
                f"✅ Raportul tău **#{report_id}** a fost trimis staff-ului!\n"
                f"**Utilizator raportat:** {reported_member.mention}\n"
                f"Vei fi notificat când staff-ul îl procesează."
            ),
            ephemeral=True
        )


# ─── Report embed builder ─────────────────────────────────────────────────────

def build_report_embed(report_id: int, reporter: discord.Member, reported: discord.Member,
                        reason: str, evidence: str, status: str,
                        handler: discord.Member = None) -> discord.Embed:
    status_emoji, status_label, status_color = STATUS_CONFIG.get(status, ("🟡", "În așteptare", 0xFEE75C))

    e = discord.Embed(
        title=f"📋 Raport #{report_id}",
        color=status_color,
        timestamp=datetime.now(timezone.utc)
    )
    e.add_field(name="🎯 Utilizator raportat",
                value=f"{reported.mention}\n`{reported}` • ID: `{reported.id}`", inline=True)
    e.add_field(name="📣 Raportat de",
                value=f"{reporter.mention}\n`{reporter}`", inline=True)
    e.add_field(name="⚡ Status",
                value=f"{status_emoji} **{status_label}**", inline=True)
    e.add_field(name="📝 Motiv",
                value=f"```{reason}```", inline=False)
    e.add_field(name="🔍 Dovezi",
                value=evidence if evidence and evidence != "Fără dovezi" else "*Nu au fost furnizate dovezi*",
                inline=False)

    if handler:
        e.add_field(name="👮 Procesat de", value=handler.mention, inline=True)

    e.set_thumbnail(url=reported.display_avatar.url)
    e.set_footer(text=f"GDP Community • Report #{report_id}")
    return e


# ─── Action buttons view ─────────────────────────────────────────────────────

class ReportActionView(discord.ui.View):
    def __init__(self, report_id: int):
        super().__init__(timeout=None)
        self.report_id = report_id

    @discord.ui.button(label="În curs", style=discord.ButtonStyle.primary,
                       emoji="🔵", custom_id="report_reviewing")
    async def reviewing_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_status(interaction, "reviewing")

    @discord.ui.button(label="Acceptat — Warn", style=discord.ButtonStyle.success,
                       emoji="⚠️", custom_id="report_accept_warn")
    async def accept_warn_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, "accepted", warn=True)

    @discord.ui.button(label="Acceptat — Ban", style=discord.ButtonStyle.danger,
                       emoji="🔨", custom_id="report_accept_ban")
    async def accept_ban_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, "banned", ban=True)

    @discord.ui.button(label="Respins", style=discord.ButtonStyle.secondary,
                       emoji="❌", custom_id="report_dismiss")
    async def dismiss_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, "dismissed")

    async def _get_report_and_check_perms(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message(
                embed=error_embed("Doar staff-ul poate procesa rapoarte."), ephemeral=True
            )
            return None
        report = await db.get_report(self.report_id)
        if not report:
            await interaction.response.send_message(
                embed=error_embed("Raportul nu mai există în baza de date."), ephemeral=True
            )
            return None
        return report

    async def _update_status(self, interaction: discord.Interaction, status: str):
        report = await self._get_report_and_check_perms(interaction)
        if not report:
            return

        await db.update_report(self.report_id, status, interaction.user.id, now_iso())

        reporter = interaction.guild.get_member(report["reporter_id"])
        reported = interaction.guild.get_member(report["reported_id"])

        if reporter and reported:
            new_embed = build_report_embed(
                self.report_id, reporter, reported,
                report["reason"], report["evidence"], status, interaction.user
            )
            await interaction.message.edit(embed=new_embed, view=self)

        await interaction.response.send_message(
            embed=success_embed(f"Raportul **#{self.report_id}** marcat ca **În curs** de tine."),
            ephemeral=True
        )

    async def _handle_action(self, interaction: discord.Interaction, status: str,
                              warn: bool = False, ban: bool = False):
        report = await self._get_report_and_check_perms(interaction)
        if not report:
            return

        await interaction.response.defer()

        reporter = interaction.guild.get_member(report["reporter_id"])
        reported = interaction.guild.get_member(report["reported_id"])

        # Apply moderation action
        action_result = ""
        if reported:
            if warn:
                warn_id = await db.add_warning(
                    reported.id, interaction.guild.id, interaction.user.id,
                    f"Raport #{self.report_id}: {report['reason']}", now_iso()
                )
                action_result = f"⚠️ Avertisment #{warn_id} aplicat lui {reported.mention}"
                try:
                    await reported.send(embed=embed(
                        title="⚠️ Ai primit un avertisment",
                        description=(
                            f"**Server:** {interaction.guild.name}\n"
                            f"**Motiv:** Raport #{self.report_id} — {report['reason']}\n"
                            f"**Aplicat de:** Staff"
                        ),
                        color=config.COLOR_WARNING
                    ))
                except discord.Forbidden:
                    pass

            elif ban:
                try:
                    await reported.send(embed=embed(
                        title="🔨 Ai fost banat",
                        description=(
                            f"Ai fost banat de pe **{interaction.guild.name}**.\n"
                            f"**Motiv:** Raport #{self.report_id} — {report['reason']}"
                        ),
                        color=config.COLOR_ERROR
                    ))
                except discord.Forbidden:
                    pass
                try:
                    await reported.ban(
                        reason=f"Raport #{self.report_id} procesat de {interaction.user} | {report['reason']}"
                    )
                    action_result = f"🔨 **{reported}** a fost banat"
                except discord.Forbidden:
                    action_result = "❌ Nu am putut da ban (permisiuni insuficiente)"

        # Update DB
        await db.update_report(self.report_id, status, interaction.user.id, now_iso())

        # Update embed & disable buttons
        if reporter and reported:
            new_embed = build_report_embed(
                self.report_id, reporter, reported,
                report["reason"], report["evidence"], status, interaction.user
            )
            closed_view = discord.ui.View()
            await interaction.message.edit(embed=new_embed, view=closed_view)

        status_emoji, status_label, _ = STATUS_CONFIG.get(status, ("🟡", "?", 0))

        # Notify reporter
        if reporter:
            try:
                notify_desc = (
                    f"Raportul tău **#{self.report_id}** împotriva lui "
                    f"**{reported or report['reported_id']}** a fost procesat.\n"
                    f"**Status:** {status_emoji} {status_label}\n"
                    f"**Procesat de:** Staff"
                )
                if action_result:
                    notify_desc += f"\n**Acțiune aplicată:** {action_result}"
                await reporter.send(embed=embed(
                    title="📋 Raportul tău a fost procesat!",
                    description=notify_desc,
                    color=STATUS_CONFIG[status][2]
                ))
            except discord.Forbidden:
                pass

        result_msg = f"Raportul **#{self.report_id}** marcat ca **{status_label}**."
        if action_result:
            result_msg += f"\n{action_result}"
        await interaction.followup.send(embed=success_embed(result_msg), ephemeral=True)


# ─── Panel button ─────────────────────────────────────────────────────────────

class ReportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Raportează un jucător",
        style=discord.ButtonStyle.danger,
        emoji="🚨",
        custom_id="open_report_modal"
    )
    async def report_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Reports(commands.Cog, name="Rapoarte"):
    """Sistem de raportare a jucătorilor."""

    def __init__(self, bot):
        self.bot = bot
        bot.add_view(ReportPanelView())

    @app_commands.command(name="reportpanel", description="[Admin] Creează panoul de raportare în canal")
    @app_commands.checks.has_permissions(administrator=True)
    async def report_panel(self, interaction: discord.Interaction):
        e = embed(
            title="🚨 Raportare Jucător — GDP Community",
            description=(
                "Ai întâlnit un comportament toxic, cheating sau o încălcare a regulilor?\n\n"
                "**Apasă butonul de mai jos** pentru a trimite un raport staff-ului.\n\n"
                "**📌 Reguli pentru rapoarte:**\n"
                "• Furnizează dovezi clare (screenshot, clip, ID mesaj)\n"
                "• Descrie situația cât mai detaliat posibil\n"
                "• Rapoartele false vor fi sancționate\n"
                "• Raportul tău este confidențial — doar staff-ul îl vede\n\n"
                "**⏱️ Timp de răspuns:** Staff-ul va procesa raportul în cel mai scurt timp."
            ),
            color=config.COLOR_ERROR,
            thumbnail=interaction.guild.icon.url if interaction.guild.icon else None
        )
        e.set_footer(text="GDP Community • Sistem de Raportare")
        await interaction.channel.send(embed=e, view=ReportPanelView())
        await interaction.response.send_message(
            embed=success_embed("Panoul de raportare a fost creat!"), ephemeral=True
        )

    @app_commands.command(name="setreportchannel", description="[Admin] Setează canalul unde vin rapoartele")
    @app_commands.describe(channel="Canalul privat pentru staff")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_report_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "report_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Rapoartele vor fi trimise în {channel.mention}.")
        )

    @app_commands.command(name="reports", description="[Staff] Afișează rapoartele recente")
    @app_commands.describe(
        status="Filtrează după status (pending/reviewing/accepted/dismissed/banned)",
        member="Filtrează rapoartele despre un utilizator specific"
    )
    @app_commands.checks.has_permissions(kick_members=True)
    async def list_reports(self, interaction: discord.Interaction,
                            status: str = None, member: discord.Member = None):
        await interaction.response.defer(ephemeral=True)

        if member:
            reports = await db.get_reports_against(member.id, interaction.guild.id)
            title = f"📋 Rapoarte despre {member.display_name}"
        else:
            reports = await db.get_all_reports(interaction.guild.id, status)
            title = f"📋 Rapoarte recente{' — ' + status if status else ''}"

        if not reports:
            return await interaction.followup.send(
                embed=embed(title=title, description="Nu există rapoarte.", color=config.COLOR_WARNING),
                ephemeral=True
            )

        lines = []
        for r in reports[:15]:
            reporter = interaction.guild.get_member(r["reporter_id"])
            reported = interaction.guild.get_member(r["reported_id"])
            s_emoji, s_label, _ = STATUS_CONFIG.get(r["status"], ("🟡", r["status"], 0))
            reporter_name = reporter.display_name if reporter else f"ID:{r['reporter_id']}"
            reported_name = reported.display_name if reported else f"ID:{r['reported_id']}"
            lines.append(
                f"{s_emoji} **#{r['id']}** — {reported_name} (raportat de {reporter_name})\n"
                f"　└ _{r['reason'][:60]}{'...' if len(r['reason']) > 60 else ''}_"
            )

        e = embed(title=title, description="\n".join(lines), color=config.COLOR_ERROR)
        e.set_footer(text=f"Total: {len(reports)} raport(e)")
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="reportinfo", description="[Staff] Afișează detaliile unui raport")
    @app_commands.describe(report_id="ID-ul raportului")
    @app_commands.checks.has_permissions(kick_members=True)
    async def report_info(self, interaction: discord.Interaction, report_id: int):
        report = await db.get_report(report_id)
        if not report or report["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message(
                embed=error_embed(f"Raportul **#{report_id}** nu a fost găsit."), ephemeral=True
            )
        reporter = interaction.guild.get_member(report["reporter_id"])
        reported = interaction.guild.get_member(report["reported_id"])
        handler = interaction.guild.get_member(report["handled_by"]) if report.get("handled_by") else None

        e = build_report_embed(
            report_id,
            reporter or interaction.user,
            reported or interaction.user,
            report["reason"],
            report["evidence"] or "Fără dovezi",
            report["status"],
            handler
        )
        if report.get("channel_id") and report.get("message_id"):
            e.add_field(
                name="🔗 Link mesaj",
                value=f"[Sari la raport](https://discord.com/channels/{interaction.guild.id}/{report['channel_id']}/{report['message_id']})",
                inline=True
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="report", description="Raportează un jucător direct prin comandă")
    @app_commands.describe(
        member="Utilizatorul pe care vrei să-l raportezi",
        reason="Motivul raportului",
        evidence="Dovezi (link sau descriere)"
    )
    async def report_cmd(self, interaction: discord.Interaction,
                          member: discord.Member, reason: str, evidence: str = "Fără dovezi"):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("Nu te poți raporta pe tine însuți."), ephemeral=True
            )
        if member.bot:
            return await interaction.response.send_message(
                embed=error_embed("Nu poți raporta un bot."), ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        report_id = await db.create_report(
            interaction.guild.id, interaction.user.id, member.id,
            reason, evidence, now_iso()
        )

        settings = await db.get_guild_settings(interaction.guild.id)
        report_ch_id = settings.get("report_channel") or 0

        if not report_ch_id:
            return await interaction.followup.send(
                embed=warning_embed(
                    f"Raportul **#{report_id}** înregistrat, dar nu există canal de rapoarte configurat.\n"
                    "Contactează un administrator."
                ),
                ephemeral=True
            )

        report_ch = interaction.guild.get_channel(report_ch_id)
        if not report_ch:
            return await interaction.followup.send(
                embed=error_embed("Canalul de rapoarte nu mai există."), ephemeral=True
            )

        report_embed = build_report_embed(
            report_id, interaction.user, member, reason, evidence, "pending"
        )
        view = ReportActionView(report_id)
        msg = await report_ch.send(embed=report_embed, view=view)
        await db.set_report_message(report_id, msg.id, report_ch.id)

        await interaction.followup.send(
            embed=success_embed(
                f"✅ Raportul **#{report_id}** a fost trimis staff-ului!\n"
                f"**Utilizator raportat:** {member.mention}"
            ),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Reports(bot))
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
