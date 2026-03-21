import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed

STATUS_COLORS = {
    "pending":  (0x5865F2, "🟡 În aşteptare"),
    "accepted": (0x57F287, "✅ Acceptat"),
    "denied":   (0xED4245, "❌ Respins"),
    "reviewing":(0x00B0F4, "🔵 În analiză"),
}


def build_suggestion_embed(suggestion_id: int, author: discord.Member,
                            content: str, status: str,
                            up: int, down: int, response: str = None,
                            handler: discord.Member = None) -> discord.Embed:
    color, status_label = STATUS_COLORS.get(status, (0x5865F2, "🟡 În aşteptare"))
    total = up + down
    bar_len = 20
    up_fill = int(bar_len * up / total) if total > 0 else 0
    bar = "🟩" * up_fill + "🟥" * (bar_len - up_fill)

    e = discord.Embed(
        title=f"💡 Sugestie #{suggestion_id}",
        description=f"```{content}```",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    e.add_field(name="👤 Propus de", value=author.mention, inline=True)
    e.add_field(name="⚡ Status", value=status_label, inline=True)
    e.add_field(name="\u200b", value="\u200b", inline=True)
    e.add_field(name="📊 Voturi",
                value=f"✅ **{up}** | ❌ **{down}**\n{bar}",
                inline=False)

    if response:
        e.add_field(name="💬 Răspuns staff",
                    value=f"_{response}_" + (f"\n— {handler.mention}" if handler else ""),
                    inline=False)

    e.set_thumbnail(url=author.display_avatar.url)
    e.set_footer(text=f"GDP Community • Sugestie #{suggestion_id}")
    return e


class SuggestionVoteView(discord.ui.View):
    """View pentru fiecare sugestie: vot + butoane de staff."""

    def __init__(self, suggestion_id: int):
        super().__init__(timeout=None)
        self.suggestion_id = suggestion_id

        # Vote buttons – pentru toată lumea
        up_btn = discord.ui.Button(
            label="Votez Da", style=discord.ButtonStyle.success,
            emoji="✅", custom_id=f"sug_up_{suggestion_id}"
        )
        up_btn.callback = self._vote_up_cb
        self.add_item(up_btn)

        down_btn = discord.ui.Button(
            label="Votez Nu", style=discord.ButtonStyle.danger,
            emoji="❌", custom_id=f"sug_down_{suggestion_id}"
        )
        down_btn.callback = self._vote_down_cb
        self.add_item(down_btn)

        # Staff control buttons – doar pentru staff (manage_guild)
        accept_btn = discord.ui.Button(
            label="Acceptă", style=discord.ButtonStyle.success,
            emoji="✅", custom_id=f"sug_accept_{suggestion_id}"
        )
        accept_btn.callback = self._staff_accept_cb
        self.add_item(accept_btn)

        deny_btn = discord.ui.Button(
            label="Respinge", style=discord.ButtonStyle.danger,
            emoji="❌", custom_id=f"sug_deny_{suggestion_id}"
        )
        deny_btn.callback = self._staff_deny_cb
        self.add_item(deny_btn)

        review_btn = discord.ui.Button(
            label="În analiză", style=discord.ButtonStyle.primary,
            emoji="🔵", custom_id=f"sug_review_{suggestion_id}"
        )
        review_btn.callback = self._staff_review_cb
        self.add_item(review_btn)

    # ─── Public voting ───────────────────────────────────────────────────────

    async def _vote_up_cb(self, interaction: discord.Interaction):
        await self._vote(interaction, "up")

    async def _vote_down_cb(self, interaction: discord.Interaction):
        await self._vote(interaction, "down")

    async def _vote(self, interaction: discord.Interaction, direction: str):
        sug = await db.get_suggestion(self.suggestion_id)
        if not sug:
            return await interaction.response.send_message(
                embed=error_embed("Sugestia nu mai există."), ephemeral=True
            )
        if sug["status"] != "pending" and sug["status"] != "reviewing":
            return await interaction.response.send_message(
                embed=error_embed("Votarea s-a încheiat pentru această sugestie."), ephemeral=True
            )
        # Simple vote (no dedup for brevity — add Redis/cache for production)
        up = sug["up_votes"] + (1 if direction == "up" else 0)
        down = sug["down_votes"] + (1 if direction == "down" else 0)
        await db.update_suggestion_votes(self.suggestion_id, up, down)

        author = interaction.guild.get_member(sug["user_id"])
        if not author:
            author = interaction.user

        sug = await db.get_suggestion(self.suggestion_id)
        new_embed = build_suggestion_embed(
            self.suggestion_id, author, sug["content"], sug["status"],
            sug["up_votes"], sug["down_votes"]
        )
        await interaction.message.edit(embed=new_embed, view=self)
        await interaction.response.send_message(
            embed=success_embed("Votul tău a fost înregistrat!"), ephemeral=True
        )

    # ─── Staff actions from panel ────────────────────────────────────────────

    async def _ensure_staff_and_cog(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                embed=error_embed("Doar staff-ul poate folosi aceste butoane."), ephemeral=True
            )
            return None
        cog = interaction.client.get_cog("Sugestii")
        if not cog:
            await interaction.response.send_message(
                embed=error_embed("Cog-ul de sugestii nu este încărcat."), ephemeral=True
            )
            return None
        return cog

    async def _staff_accept_cb(self, interaction: discord.Interaction):
        cog = await self._ensure_staff_and_cog(interaction)
        if not cog:
            return
        await cog._handle_suggestion(
            interaction, self.suggestion_id, "accepted", "Acceptat din panelul de sugestii."
        )

    async def _staff_deny_cb(self, interaction: discord.Interaction):
        cog = await self._ensure_staff_and_cog(interaction)
        if not cog:
            return
        await cog._handle_suggestion(
            interaction, self.suggestion_id, "denied", "Respins din panelul de sugestii."
        )

    async def _staff_review_cb(self, interaction: discord.Interaction):
        cog = await self._ensure_staff_and_cog(interaction)
        if not cog:
            return
        await cog._handle_suggestion(
            interaction, self.suggestion_id, "reviewing", "Sugestia este în analiză (setată din panel)."
        )


class SuggestionModal(discord.ui.Modal, title="💡 Trimite o sugestie"):
    content = discord.ui.TextInput(
        label="Sugestia ta",
        placeholder="Descrie sugestia ta în detaliu...",
        style=discord.TextStyle.paragraph,
        min_length=20,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        text = self.content.value.strip()
        sug_id = await db.create_suggestion(
            interaction.guild.id, interaction.user.id, text, now_iso()
        )

        settings = await db.get_guild_settings(interaction.guild.id)
        ch_id = settings.get("suggestion_channel") or 0
        if not ch_id:
            return await interaction.followup.send(
                embed=error_embed("Nu există un canal de sugestii configurat. Contactează un admin."),
                ephemeral=True
            )

        ch = interaction.guild.get_channel(ch_id)
        if not ch:
            return await interaction.followup.send(
                embed=error_embed("Canalul de sugestii nu mai există."), ephemeral=True
            )

        sug_embed = build_suggestion_embed(
            sug_id, interaction.user, text, "pending", 0, 0
        )
        view = SuggestionVoteView(sug_id)

        msg = await ch.send(embed=sug_embed, view=view)
        await db.set_suggestion_message(sug_id, msg.id, ch.id)

        await interaction.followup.send(
            embed=success_embed(
                f"✅ Sugestia ta **#{sug_id}** a fost trimisă!\n"
                f"Membrii pot vota în {ch.mention}."
            ),
            ephemeral=True
        )


class StaffSuggestionModal(discord.ui.Modal):
    """Răspuns staff la accept / respingere — formular pe ecran."""

    def __init__(self, cog: "Suggestions", suggestion_id: int, status: str, default_title: str):
        super().__init__(title=default_title, timeout=300)
        self.cog = cog
        self.suggestion_id = suggestion_id
        self.status = status
        self.response_text = discord.ui.TextInput(
            label="Mesaj public / motiv",
            style=discord.TextStyle.paragraph,
            placeholder="Ex: Acceptat — vom implementa în săptămâna viitoare.",
            max_length=1000,
            required=True,
        )
        self.add_item(self.response_text)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.cog._handle_suggestion_deferred(
            interaction, self.suggestion_id, self.status, self.response_text.value.strip()
        )


class SuggestionPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Trimite o sugestie", style=discord.ButtonStyle.primary,
                       emoji="💡", custom_id="open_suggestion_modal")
    async def suggest_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SuggestionModal())


class Suggestions(commands.Cog, name="Sugestii"):
    """Sistem de sugestii cu vot."""

    def __init__(self, bot):
        self.bot = bot
        bot.add_view(SuggestionPanelView())

    @app_commands.command(name="suggestionpanel", description="[Admin] Creează panoul de sugestii")
    @app_commands.checks.has_permissions(administrator=True)
    async def suggestion_panel(self, interaction: discord.Interaction):
        e = embed(
            title="💡 Sistem de Sugestii — GDP Community",
            description=(
                "Ai o idee care ar îmbunătăți serverul?\n\n"
                "**Apasă butonul** pentru a trimite sugestia ta.\n\n"
                "📌 **Reguli:**\n"
                "• Fii detaliat și constructiv\n"
                "• O sugestie per mesaj\n"
                "• Fără sugestii duplicate\n"
                "• Respectă regulile serverului\n\n"
                "Sugestiile aprobate vor fi implementate! 🚀"
            ),
            color=config.COLOR_PRIMARY,
            thumbnail=interaction.guild.icon.url if interaction.guild.icon else None
        )
        await interaction.channel.send(embed=e, view=SuggestionPanelView())
        await interaction.response.send_message(
            embed=success_embed("Panoul de sugestii a fost creat!"), ephemeral=True
        )

    @app_commands.command(name="setsuggestionchannel", description="[Admin] Setează canalul de sugestii")
    @app_commands.describe(channel="Canalul unde apar sugestiile")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_suggestion_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "suggestion_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal de sugestii setat la {channel.mention}.")
        )

    @app_commands.command(name="suggest", description="Trimite o sugestie (formular pe ecran)")
    async def suggest_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SuggestionModal())

    @app_commands.command(name="accept", description="[Staff] Acceptă o sugestie (formular pentru răspuns)")
    @app_commands.describe(suggestion_id="ID-ul sugestiei")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def accept_suggestion(self, interaction: discord.Interaction, suggestion_id: int):
        await interaction.response.send_modal(
            StaffSuggestionModal(self, suggestion_id, "accepted", "✅ Acceptă sugestia")
        )

    @app_commands.command(name="deny", description="[Staff] Respinge o sugestie (formular pentru motiv)")
    @app_commands.describe(suggestion_id="ID-ul sugestiei")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def deny_suggestion(self, interaction: discord.Interaction, suggestion_id: int):
        await interaction.response.send_modal(
            StaffSuggestionModal(self, suggestion_id, "denied", "❌ Respinge sugestia")
        )

    @app_commands.command(name="review", description="[Staff] Marchează o sugestie ca în analiză")
    @app_commands.describe(suggestion_id="ID-ul sugestiei")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def review_suggestion(self, interaction: discord.Interaction, suggestion_id: int):
        await self._handle_suggestion(interaction, suggestion_id, "reviewing", "Sugestia este în analiză.")

    async def _handle_suggestion_deferred(
        self, interaction: discord.Interaction, suggestion_id: int, status: str, response: str
    ):
        """Folosit după modal — interaction e deja defer(ephemeral)."""
        sug = await db.get_suggestion(suggestion_id)
        if not sug or sug["guild_id"] != interaction.guild.id:
            return await interaction.followup.send(
                embed=error_embed(f"Sugestia #{suggestion_id} nu există."), ephemeral=True
            )

        await db.update_suggestion(suggestion_id, status, response, interaction.user.id)
        sug = await db.get_suggestion(suggestion_id)

        author = interaction.guild.get_member(sug["user_id"])
        if not author:
            return await interaction.followup.send(
                embed=error_embed("Autorul sugestiei nu mai este pe server."), ephemeral=True
            )

        new_embed = build_suggestion_embed(
            suggestion_id, author, sug["content"], status,
            sug["up_votes"], sug["down_votes"], response, interaction.user
        )

        if sug.get("channel_id") and sug.get("message_id"):
            try:
                ch = interaction.guild.get_channel(sug["channel_id"])
                msg = await ch.fetch_message(sug["message_id"])
                await msg.edit(embed=new_embed, view=None)
            except Exception:
                pass

        color, status_label = STATUS_COLORS.get(status, (0x5865F2, status))
        try:
            await author.send(embed=embed(
                title=f"💡 Sugestia ta #{suggestion_id} a primit un răspuns!",
                description=(
                    f"**Status:** {status_label}\n"
                    f"**Răspuns:** {response}\n"
                    f"**Procesat de:** {interaction.user.mention}"
                ),
                color=color
            ))
        except discord.Forbidden:
            pass

        await interaction.followup.send(
            embed=success_embed(f"Sugestia #{suggestion_id} marcată ca **{status_label}**."),
            ephemeral=True
        )

    async def _handle_suggestion(self, interaction: discord.Interaction,
                                   suggestion_id: int, status: str, response: str):
        sug = await db.get_suggestion(suggestion_id)
        if not sug or sug["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message(
                embed=error_embed(f"Sugestia #{suggestion_id} nu există."), ephemeral=True
            )

        await db.update_suggestion(suggestion_id, status, response, interaction.user.id)
        sug = await db.get_suggestion(suggestion_id)

        author = interaction.guild.get_member(sug["user_id"])
        if not author:
            return await interaction.response.send_message(
                embed=error_embed("Autorul sugestiei nu mai este pe server."), ephemeral=True
            )

        new_embed = build_suggestion_embed(
            suggestion_id, author, sug["content"], status,
            sug["up_votes"], sug["down_votes"], response, interaction.user
        )

        # Update original message
        if sug.get("channel_id") and sug.get("message_id"):
            try:
                ch = interaction.guild.get_channel(sug["channel_id"])
                msg = await ch.fetch_message(sug["message_id"])
                await msg.edit(embed=new_embed, view=None)
            except Exception:
                pass

        # Notify author
        color, status_label = STATUS_COLORS.get(status, (0x5865F2, status))
        try:
            await author.send(embed=embed(
                title=f"💡 Sugestia ta #{suggestion_id} a primit un răspuns!",
                description=(
                    f"**Status:** {status_label}\n"
                    f"**Răspuns:** {response}\n"
                    f"**Procesat de:** {interaction.user.mention}"
                ),
                color=color
            ))
        except discord.Forbidden:
            pass

        await interaction.response.send_message(
            embed=success_embed(f"Sugestia #{suggestion_id} marcată ca **{status_label}**."),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Suggestions(bot))
