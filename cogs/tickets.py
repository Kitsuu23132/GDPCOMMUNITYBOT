import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import io
import asyncio

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed


TICKET_CATEGORIES = {
    "general":  ("❓", "Support General",  0x5865F2),
    "report":   ("🚨", "Raportare Jucător", 0xED4245),
    "appeal":   ("⚖️", "Contestație Ban",   0xFEE75C),
    "purchase": ("💰", "Probleme Cumpărare",0x57F287),
    "other":    ("📋", "Altele",            0x99AAB5),
}


# ─── Transcript generator ────────────────────────────────────────────────────

async def generate_transcript(channel: discord.TextChannel, ticket: dict, guild: discord.Guild) -> io.BytesIO:
    """Generează un transcript HTML frumos al conversației din ticket."""

    messages = []
    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(msg)

    cat_key = ticket.get("category", "general")
    emoji, cat_name, cat_color = TICKET_CATEGORIES.get(cat_key, ("❓", "General", 0x5865F2))
    hex_color = f"#{cat_color:06X}"

    owner = guild.get_member(ticket["user_id"])
    owner_name = str(owner) if owner else f"ID:{ticket['user_id']}"

    opened_at = ticket.get("created_at", "N/A")
    try:
        dt = datetime.fromisoformat(opened_at)
        opened_str = dt.strftime("%d.%m.%Y %H:%M UTC")
    except Exception:
        opened_str = opened_at

    msg_rows = []
    for msg in messages:
        if msg.author.bot and not msg.embeds and not msg.content:
            continue
        ts = msg.created_at.strftime("%d.%m.%Y %H:%M")
        avatar_url = str(msg.author.display_avatar.url)
        is_bot = msg.author.bot
        bot_badge = '<span class="badge">BOT</span>' if is_bot else ""
        name_color = "#7289da" if is_bot else "#ffffff"

        content_html = ""
        if msg.content:
            safe = (msg.content
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br>"))
            content_html += f'<div class="msg-content">{safe}</div>'

        for emb in msg.embeds:
            emb_color = f"#{emb.color.value:06X}" if emb.color else "#5865F2"
            emb_title = emb.title or ""
            emb_desc = (emb.description or "").replace("\n", "<br>")
            fields_html = ""
            for field in emb.fields:
                fields_html += f"""
                <div class="emb-field {'inline' if field.inline else ''}">
                    <div class="emb-field-name">{field.name}</div>
                    <div class="emb-field-value">{field.value.replace(chr(10), '<br>')}</div>
                </div>"""
            content_html += f"""
            <div class="embed" style="border-left:4px solid {emb_color}">
                {'<div class="emb-title">' + emb_title + '</div>' if emb_title else ''}
                {'<div class="emb-desc">' + emb_desc + '</div>' if emb_desc else ''}
                {'<div class="emb-fields">' + fields_html + '</div>' if fields_html else ''}
            </div>"""

        for att in msg.attachments:
            if att.content_type and att.content_type.startswith("image"):
                content_html += f'<div class="attachment"><img src="{att.url}" alt="attachment" style="max-width:400px;max-height:300px;border-radius:4px;margin-top:6px"></div>'
            else:
                content_html += f'<div class="attachment">📎 <a href="{att.url}" style="color:#00b0f4">{att.filename}</a></div>'

        msg_rows.append(f"""
        <div class="message {'bot-msg' if is_bot else ''}">
            <img class="avatar" src="{avatar_url}" alt="avatar">
            <div class="msg-body">
                <div class="msg-header">
                    <span class="username" style="color:{name_color}">{msg.author.display_name}</span>
                    {bot_badge}
                    <span class="timestamp">{ts}</span>
                </div>
                {content_html}
            </div>
        </div>""")

    html = f"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Transcript Ticket #{ticket['ticket_id']} — GDP Community</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #36393f;
    color: #dcddde;
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
  }}
  .header {{
    background: #2f3136;
    border-bottom: 3px solid {hex_color};
    padding: 20px 30px;
    display: flex;
    align-items: center;
    gap: 20px;
  }}
  .header-icon {{
    font-size: 40px;
  }}
  .header-info h1 {{
    font-size: 22px;
    color: #ffffff;
    font-weight: 700;
  }}
  .header-info p {{
    color: #8e9297;
    font-size: 13px;
    margin-top: 4px;
  }}
  .meta-bar {{
    background: #2f3136;
    padding: 12px 30px;
    display: flex;
    gap: 30px;
    flex-wrap: wrap;
    border-bottom: 1px solid #202225;
  }}
  .meta-item {{
    display: flex;
    flex-direction: column;
  }}
  .meta-label {{
    font-size: 11px;
    text-transform: uppercase;
    color: #8e9297;
    font-weight: 600;
    letter-spacing: 0.5px;
  }}
  .meta-value {{
    color: #ffffff;
    font-size: 14px;
    font-weight: 500;
    margin-top: 2px;
  }}
  .messages {{
    padding: 20px 30px;
    max-width: 900px;
    margin: 0 auto;
  }}
  .message {{
    display: flex;
    gap: 14px;
    padding: 8px 0;
    border-radius: 4px;
  }}
  .message:hover {{
    background: #32353b;
    padding-left: 6px;
    margin-left: -6px;
  }}
  .bot-msg {{ opacity: 0.9; }}
  .avatar {{
    width: 40px;
    height: 40px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 2px;
  }}
  .msg-body {{
    flex: 1;
    min-width: 0;
  }}
  .msg-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }}
  .username {{
    font-weight: 600;
    font-size: 15px;
  }}
  .badge {{
    background: #5865f2;
    color: white;
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
    text-transform: uppercase;
  }}
  .timestamp {{
    color: #72767d;
    font-size: 12px;
  }}
  .msg-content {{
    color: #dcddde;
    line-height: 1.5;
    word-wrap: break-word;
  }}
  .embed {{
    margin-top: 6px;
    background: #2f3136;
    border-radius: 4px;
    padding: 12px 14px;
    max-width: 520px;
  }}
  .emb-title {{
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 6px;
  }}
  .emb-desc {{
    color: #dcddde;
    font-size: 13px;
    line-height: 1.5;
  }}
  .emb-fields {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 8px;
  }}
  .emb-field {{
    min-width: 120px;
  }}
  .emb-field.inline {{
    flex: 1;
  }}
  .emb-field-name {{
    font-size: 12px;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 2px;
  }}
  .emb-field-value {{
    font-size: 13px;
    color: #dcddde;
  }}
  .divider {{
    border: none;
    border-top: 1px solid #40444b;
    margin: 8px 0;
  }}
  .footer {{
    text-align: center;
    padding: 20px;
    color: #72767d;
    font-size: 12px;
    border-top: 1px solid #40444b;
    margin-top: 20px;
  }}
  .msg-count {{
    background: {hex_color};
    color: white;
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
  }}
</style>
</head>
<body>

<div class="header">
  <div class="header-icon">{emoji}</div>
  <div class="header-info">
    <h1>Transcript Ticket #{ticket['ticket_id']}</h1>
    <p>GDP Community — {cat_name}</p>
  </div>
</div>

<div class="meta-bar">
  <div class="meta-item">
    <span class="meta-label">Utilizator</span>
    <span class="meta-value">{owner_name}</span>
  </div>
  <div class="meta-item">
    <span class="meta-label">Categorie</span>
    <span class="meta-value">{emoji} {cat_name}</span>
  </div>
  <div class="meta-item">
    <span class="meta-label">Deschis la</span>
    <span class="meta-value">{opened_str}</span>
  </div>
  <div class="meta-item">
    <span class="meta-label">Canal</span>
    <span class="meta-value">#{channel.name}</span>
  </div>
  <div class="meta-item">
    <span class="meta-label">Mesaje</span>
    <span class="meta-value"><span class="msg-count">{len(messages)}</span></span>
  </div>
</div>

<div class="messages">
  {'<hr class="divider">'.join(msg_rows) if msg_rows else '<p style="color:#72767d;text-align:center;padding:40px">Nu există mesaje în acest ticket.</p>'}
</div>

<div class="footer">
  Transcript generat automat de GDP Community Bot • {datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")}
</div>

</body>
</html>"""

    return io.BytesIO(html.encode("utf-8"))


# ─── Views ───────────────────────────────────────────────────────────────────

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(
        placeholder="Selectează categoria ticketului...",
        custom_id="ticket_category_select",
        options=[
            discord.SelectOption(label=v[1], value=k, emoji=v[0])
            for k, v in TICKET_CATEGORIES.items()
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        category = select.values[0]
        await open_ticket(interaction, category)


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Închide Ticket", style=discord.ButtonStyle.danger,
                       emoji="🔒", custom_id="close_ticket_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await close_ticket(interaction)

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.primary,
                       emoji="🙋", custom_id="claim_ticket_btn")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                embed=error_embed("Doar staff-ul poate prelua tickete."), ephemeral=True
            )
        overwrite = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        await interaction.channel.set_permissions(interaction.user, overwrite=overwrite)
        await interaction.response.send_message(embed=embed(
            title="🙋 Ticket preluat",
            description=f"{interaction.user.mention} a preluat acest ticket.",
            color=config.COLOR_SUCCESS
        ))

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary,
                       emoji="📄", custom_id="transcript_ticket_btn")
    async def transcript_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                embed=error_embed("Doar staff-ul poate genera transcript-uri."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            return await interaction.followup.send(
                embed=error_embed("Acesta nu este un canal de ticket."), ephemeral=True
            )
        transcript_bytes = await generate_transcript(interaction.channel, ticket, interaction.guild)
        file = discord.File(transcript_bytes, filename=f"transcript-ticket-{ticket['ticket_id']}.html")
        await interaction.followup.send(
            embed=success_embed("Transcript generat! Deschide fișierul HTML în browser."),
            file=file,
            ephemeral=True
        )


# ─── Open / Close ticket logic ───────────────────────────────────────────────

async def open_ticket(interaction: discord.Interaction, category: str):
    guild = interaction.guild
    settings = await db.get_guild_settings(guild.id)
    cat_id = settings.get("ticket_category_id") or config.TICKET_CATEGORY_ID

    existing = discord.utils.get(
        guild.text_channels,
        name=f"ticket-{interaction.user.name.lower().replace(' ', '-')}"
    )
    if existing:
        ticket_data = await db.get_ticket_by_channel(existing.id)
        if ticket_data and ticket_data["status"] == "open":
            return await interaction.response.send_message(
                embed=error_embed(f"Ai deja un ticket deschis: {existing.mention}"),
                ephemeral=True
            )

    emoji, cat_name, cat_color = TICKET_CATEGORIES.get(category, ("❓", "General", 0x5865F2))
    category_obj = guild.get_channel(cat_id) if cat_id else None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, attach_files=True
        ),
        guild.me: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, manage_channels=True
        ),
    }

    mod_role_id = settings.get("mod_role") or config.MOD_ROLE_ID
    if mod_role_id:
        mod_role = guild.get_role(mod_role_id)
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            )

    ch_name = f"ticket-{interaction.user.name.lower()[:20]}"
    channel = await guild.create_text_channel(
        ch_name,
        category=category_obj,
        overwrites=overwrites,
        topic=f"Ticket deschis de {interaction.user} | {cat_name}"
    )

    ticket_id = await db.create_ticket(
        guild.id, interaction.user.id, channel.id, category, now_iso()
    )

    e = embed(
        title=f"{emoji} Ticket #{ticket_id} — {cat_name}",
        description=(
            f"Bun venit {interaction.user.mention}!\n"
            f"Descrie problema ta și staff-ul te va ajuta în cel mai scurt timp.\n\n"
            f"**Categorie:** {cat_name}\n"
            f"**ID Ticket:** `#{ticket_id}`"
        ),
        color=cat_color,
        thumbnail=interaction.user.display_avatar.url
    )
    await channel.send(
        content=f"{interaction.user.mention}",
        embed=e,
        view=CloseTicketView()
    )

    await interaction.response.send_message(
        embed=success_embed(f"Ticketul tău a fost creat: {channel.mention}"),
        ephemeral=True
    )

    log_ch_id = settings.get("ticket_log_channel") or config.TICKET_LOG_CHANNEL_ID
    if log_ch_id:
        log_ch = guild.get_channel(log_ch_id)
        if log_ch:
            await log_ch.send(embed=embed(
                title="🎫 Ticket deschis",
                color=cat_color,
                fields=[
                    ("Utilizator", f"{interaction.user.mention} (`{interaction.user.id}`)", True),
                    ("Canal", channel.mention, True),
                    ("Categorie", cat_name, True),
                    ("ID Ticket", f"#{ticket_id}", True),
                ]
            ))


async def close_ticket(interaction: discord.Interaction):
    ticket = await db.get_ticket_by_channel(interaction.channel.id)
    if not ticket:
        return await interaction.response.send_message(
            embed=error_embed("Acesta nu este un canal de ticket."), ephemeral=True
        )
    if ticket["status"] == "closed":
        return await interaction.response.send_message(
            embed=error_embed("Ticketul este deja închis."), ephemeral=True
        )

    can_close = (
        interaction.user.id == ticket["user_id"]
        or interaction.user.guild_permissions.manage_channels
    )
    if not can_close:
        return await interaction.response.send_message(
            embed=error_embed("Nu ai permisiunea să închizi acest ticket."), ephemeral=True
        )

    await interaction.response.defer()

    # Generate transcript o singură dată
    transcript_bytes = await generate_transcript(interaction.channel, ticket, interaction.guild)
    transcript_data = transcript_bytes.getvalue()
    filename = f"transcript-ticket-{ticket['ticket_id']}.html"

    settings = await db.get_guild_settings(interaction.guild.id)
    log_ch_id = settings.get("ticket_log_channel") or config.TICKET_LOG_CHANNEL_ID
    cat_key = ticket.get("category", "general")
    emoji, cat_name, cat_color = TICKET_CATEGORIES.get(cat_key, ("❓", "General", 0x5865F2))

    owner = interaction.guild.get_member(ticket["user_id"])
    log_embed = embed(
        title=f"🔒 Ticket #{ticket['ticket_id']} închis",
        color=config.COLOR_WARNING,
        fields=[
            ("Utilizator", f"{owner.mention if owner else ticket['user_id']}", True),
            ("Închis de", interaction.user.mention, True),
            ("Categorie", f"{emoji} {cat_name}", True),
            ("Canal", f"#{interaction.channel.name}", True),
        ]
    )

    if log_ch_id:
        log_ch = interaction.guild.get_channel(log_ch_id)
        if log_ch:
            await log_ch.send(embed=log_embed, file=discord.File(io.BytesIO(transcript_data), filename=filename))

    if owner:
        try:
            await owner.send(
                embed=embed(
                    title=f"📄 Transcript Ticket #{ticket['ticket_id']}",
                    description=(
                        f"Ticketul tău de pe **{interaction.guild.name}** a fost închis.\n"
                        f"**Categorie:** {emoji} {cat_name}\n\n"
                        f"Transcriptul conversației este atașat mai jos.\n"
                        f"*Deschide fișierul `.html` în orice browser.*"
                    ),
                    color=cat_color
                ),
                file=discord.File(io.BytesIO(transcript_data), filename=filename)
            )
        except discord.Forbidden:
            pass

    await db.close_ticket(interaction.channel.id, now_iso())

    await interaction.followup.send(embed=embed(
        title="🔒 Ticket închis",
        description=(
            f"Ticketul a fost închis de {interaction.user.mention}.\n"
            f"📄 Transcriptul a fost trimis în DM și în canalul de log.\n"
            f"Canalul va fi șters în **5 secunde**."
        ),
        color=config.COLOR_WARNING
    ))

    await asyncio.sleep(5)
    try:
        await interaction.channel.delete(reason=f"Ticket închis de {interaction.user}")
    except Exception:
        pass


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog, name="Tickets"):
    """Sistem de tickete de support cu transcript HTML."""

    def __init__(self, bot):
        self.bot = bot
        bot.add_view(TicketView())
        bot.add_view(CloseTicketView())

    @app_commands.command(name="ticket", description="Creează panoul de tickete în canal")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(self, interaction: discord.Interaction):
        e = embed(
            title="🎫 Sistem de Support — GDP Community",
            description=(
                "Ai nevoie de ajutor? Selectează categoria de mai jos pentru a deschide un ticket.\n\n"
                "❓ **Support General** — Întrebări și probleme generale\n"
                "🚨 **Raportare Jucător** — Raportează un comportament toxic\n"
                "⚖️ **Contestație Ban** — Contestă un ban sau mute\n"
                "💰 **Probleme Cumpărare** — Probleme cu donații/shop\n"
                "📋 **Altele** — Orice altceva\n\n"
                "*Staff-ul va răspunde cât mai curând posibil.*"
            ),
            color=config.COLOR_PRIMARY
        )
        await interaction.channel.send(embed=e, view=TicketView())
        await interaction.response.send_message(
            embed=success_embed("Panoul de tickete a fost creat!"), ephemeral=True
        )

    @app_commands.command(name="closeticket", description="Închide ticketul curent și generează transcript")
    async def closeticket(self, interaction: discord.Interaction):
        await close_ticket(interaction)

    @app_commands.command(name="transcript", description="Generează transcriptul ticketului curent")
    async def transcript_cmd(self, interaction: discord.Interaction):
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                embed=error_embed("Acesta nu este un canal de ticket."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        transcript_bytes = await generate_transcript(interaction.channel, ticket, interaction.guild)
        file = discord.File(transcript_bytes, filename=f"transcript-ticket-{ticket['ticket_id']}.html")
        await interaction.followup.send(
            embed=success_embed(
                f"📄 Transcript generat pentru **Ticket #{ticket['ticket_id']}**!\n"
                f"Deschide fișierul `.html` în orice browser (Chrome, Firefox etc.)"
            ),
            file=file,
            ephemeral=True
        )

    @app_commands.command(name="adduser", description="Adaugă un utilizator la ticketul curent")
    @app_commands.describe(member="Utilizatorul de adăugat")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def adduser(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                embed=error_embed("Acesta nu este un canal de ticket."), ephemeral=True
            )
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)
        await interaction.response.send_message(
            embed=success_embed(f"{member.mention} a fost adăugat la ticket.")
        )

    @app_commands.command(name="removeuser", description="Elimină un utilizator din ticketul curent")
    @app_commands.describe(member="Utilizatorul de eliminat")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def removeuser(self, interaction: discord.Interaction, member: discord.Member):
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                embed=error_embed("Acesta nu este un canal de ticket."), ephemeral=True
            )
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(
            embed=success_embed(f"{member.mention} a fost eliminat din ticket.")
        )


async def setup(bot):
    await bot.add_cog(Tickets(bot))
