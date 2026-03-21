<<<<<<< HEAD
import discord
from discord.ext import commands
from discord import app_commands, AuditLogAction
from datetime import datetime, timezone

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed


LOG_CHANNELS_MAP = {
    "msg_delete":      "🗑️ Mesaje şterse",
    "msg_edit":        "✏️ Mesaje editate",
    "member_join":     "📥 Membri join",
    "member_leave":    "📤 Membri leave",
    "member_ban":      "🔨 Banuri",
    "member_unban":    "✅ Debanuri",
    "role_update":     "🎭 Roluri",
    "voice_activity":  "🔊 Voce",
    "nickname_change": "📛 Nickname",
    "invite_track":    "🔗 Invite",
}

AUTO_CHANNELS = {
    "msg_delete":     "log-mesaje",
    "msg_edit":       "log-mesaje",
    "member_join":    "log-membri",
    "member_leave":   "log-membri",
    "member_ban":     "log-moderare",
    "member_unban":   "log-moderare",
    "role_update":    "log-server",
    "voice_activity": "log-voice",
    "nickname_change":"log-membri",
    "invite_track":   "log-membri",
}

# Categoria preferată pentru loguri (dacă există deja pe server)
LOG_CATEGORY_ID = 1452797800088866970


class EventLog(commands.Cog, name="Logging"):
    """Sistem avansat de logging al evenimentelor."""

    def __init__(self, bot):
        self.bot = bot
        self._invite_cache: dict[int, dict[str, int]] = {}

    async def _get_logs_category(self, guild: discord.Guild) -> discord.CategoryChannel | None:
        """Returnează categoria în care se vor crea canalele de log.

        1) Încearcă categoria cu ID-ul fixat (LOG_CATEGORY_ID).
        2) Dacă nu există sau nu e categorie, folosește/creează „📋 GDP Logs”.
        """
        category = guild.get_channel(LOG_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(guild.categories, name="📋 GDP Logs")
            if not category:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                }
                # Rolurile cu administrator au acces la loguri
                for role in guild.roles:
                    if role.permissions.administrator:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=True)
                category = await guild.create_category("📋 GDP Logs", overwrites=overwrites)
        return category

    async def _auto_setup_logging_for_guild(self, guild: discord.Guild):
        """Se asigură că toate canalele de log există pentru un guild.

        Este idempotent: dacă există deja canalele, doar actualizează ID-urile în DB.
        """
        category = await self._get_logs_category(guild)
        if category is None:
            return

        channels_config = {
            "log-mesaje":    ["msg_delete", "msg_edit"],
            "log-membri":    ["member_join", "member_leave", "nickname_change", "invite_track"],
            "log-moderare":  ["member_ban", "member_unban"],
            "log-voice":     ["voice_activity"],
            "log-server":    ["role_update"],
        }

        for ch_name, log_types in channels_config.items():
            ch = discord.utils.get(category.text_channels, name=ch_name)
            if not ch:
                ch = await guild.create_text_channel(ch_name, category=category)
            for lt in log_types:
                await db.set_log_channel(guild.id, lt, ch.id)

    async def _send_log(self, guild: discord.Guild, log_type: str, embed_data: discord.Embed):
        channels = await db.get_log_channels(guild.id)
        ch_id = channels.get(log_type, 0)
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if ch:
            try:
                await ch.send(embed=embed_data)
            except Exception:
                pass

    # ─── Auto-setup la pornirea botului ───────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        # La pornire / reconectare, ne asigurăm că fiecare guild are canalele de log
        for guild in self.bot.guilds:
            try:
                await self._auto_setup_logging_for_guild(guild)
            except Exception:
                # Nu blocăm on_ready dacă un guild dă eroare
                continue

    @app_commands.command(name="setlogchannel2", description="[Admin] Setează manual un canal de log")
    @app_commands.describe(
        log_type="Tipul de log (msg_delete/msg_edit/member_join/etc.)",
        channel="Canalul de log"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel_manual(self, interaction: discord.Interaction,
                                      log_type: str, channel: discord.TextChannel):
        if log_type not in LOG_CHANNELS_MAP:
            types = ", ".join(f"`{k}`" for k in LOG_CHANNELS_MAP)
            return await interaction.response.send_message(
                embed=error_embed(f"Tip invalid. Tipuri disponibile:\n{types}"), ephemeral=True
            )
        await db.set_log_channel(interaction.guild.id, log_type, channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Log `{log_type}` → {channel.mention}.")
        )

    @app_commands.command(name="logstatus", description="[Admin] Afişează canalele de log configurate")
    @app_commands.checks.has_permissions(administrator=True)
    async def log_status(self, interaction: discord.Interaction):
        channels = await db.get_log_channels(interaction.guild.id)
        lines = []
        for key, label in LOG_CHANNELS_MAP.items():
            ch_id = channels.get(key, 0)
            ch = interaction.guild.get_channel(ch_id) if ch_id else None
            status = ch.mention if ch else "❌ Nesetat"
            lines.append(f"{label}: {status}")
        await interaction.response.send_message(embed=embed(
            title="📋 Status Logging",
            description="\n".join(lines),
            color=config.COLOR_PRIMARY
        ), ephemeral=True)

    # ─── Message delete ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        e = embed(
            title="🗑️ Mesaj şters",
            color=config.COLOR_ERROR,
            fields=[
                ("Autor", f"{message.author.mention} (`{message.author.id}`)", True),
                ("Canal", message.channel.mention, True),
                ("Conținut", f"```{message.content[:900] or 'fără text'}```", False),
            ],
        )
        e.set_thumbnail(url=message.author.display_avatar.url)
        if message.attachments:
            e.add_field(name="Fişiere", value="\n".join(a.filename for a in message.attachments), inline=False)
        await self._send_log(message.guild, "msg_delete", e)

    # ─── Message edit ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return
        e = embed(
            title="✏️ Mesaj editat",
            color=config.COLOR_WARNING,
            fields=[
                ("Autor", f"{before.author.mention} (`{before.author.id}`)", True),
                ("Canal", before.channel.mention, True),
                ("Link", f"[Sari la mesaj]({after.jump_url})", True),
                ("Înainte", f"```{before.content[:450] or 'gol'}```", False),
                ("După", f"```{after.content[:450] or 'gol'}```", False),
            ],
        )
        e.set_thumbnail(url=before.author.display_avatar.url)
        await self._send_log(before.guild, "msg_edit", e)

    # ─── Member join ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        account_age = (datetime.now(timezone.utc) - member.created_at).days
        suspicious = account_age < 7
        e = embed(
            title="📥 Membru nou",
            color=config.COLOR_SUCCESS if not suspicious else config.COLOR_WARNING,
            fields=[
                ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                ("Tag", str(member), True),
                ("Cont creat", f"<t:{int(member.created_at.timestamp())}:R> ({account_age}z)", True),
                ("Membri totali", str(member.guild.member_count), True),
                ("⚠️ Cont nou", "DA — verificați!" if suspicious else "Nu", True),
            ],
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, "member_join", e)

    # ─── Member leave ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        e = embed(
            title="📤 Membru plecat",
            color=config.COLOR_ERROR,
            fields=[
                ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                ("Tag", str(member), True),
                ("Roluri", " ".join(roles[:8]) or "Niciunul", False),
            ],
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, "member_leave", e)

    # ─── Ban / Unban ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        responsible = "necunoscut"
        try:
            async for entry in guild.audit_logs(limit=5, action=AuditLogAction.ban):
                if entry.target.id == user.id:
                    responsible = f"{entry.user.mention} (`{entry.user.id}`)"
                    break
        except discord.Forbidden:
            responsible = "necunoscut (fără permisiune la audit log)"

        e = embed(
            title="🔨 Utilizator banat",
            color=config.COLOR_ERROR,
            fields=[
                ("Utilizator", f"{user.mention} (`{user.id}`)", True),
                ("Responsabil", responsible, True),
                ("Tag", str(user), True),
            ],
        )
        e.set_thumbnail(url=user.display_avatar.url)
        await self._send_log(guild, "member_ban", e)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        responsible = "necunoscut"
        try:
            async for entry in guild.audit_logs(limit=5, action=AuditLogAction.unban):
                if entry.target.id == user.id:
                    responsible = f"{entry.user.mention} (`{entry.user.id}`)"
                    break
        except discord.Forbidden:
            responsible = "necunoscut (fără permisiune la audit log)"

        e = embed(
            title="✅ Utilizator debanat",
            color=config.COLOR_SUCCESS,
            fields=[
                ("Utilizator", f"{user.mention} (`{user.id}`)", True),
                ("Responsabil", responsible, True),
            ],
        )
        await self._send_log(guild, "member_unban", e)

    # ─── Nickname change ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick and before.roles == after.roles:
            return

        if before.nick != after.nick:
            e = embed(
                title="📛 Nickname schimbat",
                color=config.COLOR_INFO,
                fields=[
                    ("Utilizator", f"{after.mention} (`{after.id}`)", True),
                    ("Înainte", before.nick or before.name, True),
                    ("După", after.nick or after.name, True),
                ],
            )
            e.set_thumbnail(url=after.display_avatar.url)
            await self._send_log(after.guild, "nickname_change", e)

        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            if not added and not removed:
                return
            fields = [("Utilizator", f"{after.mention} (`{after.id}`)", True)]
            if added:
                fields.append(("Roluri adăugate", " ".join(r.mention for r in added), False))
            if removed:
                fields.append(("Roluri eliminate", " ".join(r.mention for r in removed), False))

            responsible = "necunoscut"
            try:
                async for entry in after.guild.audit_logs(limit=5, action=AuditLogAction.member_role_update):
                    if entry.target.id == after.id:
                        responsible = f"{entry.user.mention} (`{entry.user.id}`)"
                        break
            except discord.Forbidden:
                responsible = "necunoscut (fără permisiune la audit log)"

            fields.append(("Responsabil", responsible, False))
            e = embed(title="🎭 Roluri modificate", color=config.COLOR_INFO, fields=fields)
            e.set_thumbnail(url=after.display_avatar.url)
            await self._send_log(after.guild, "role_update", e)

    # ─── Voice activity ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                     before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        if before.channel == after.channel:
            return

        if after.channel and not before.channel:
            e = embed(
                title="🔊 Intrat în voice",
                color=0x2ECC71,
                fields=[
                    ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                    ("Canal", after.channel.mention, True),
                ],
            )
            await self._send_log(member.guild, "voice_activity", e)
        elif before.channel and not after.channel:
            e = embed(
                title="🔇 Ieşit din voice",
                color=0xE74C3C,
                fields=[
                    ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                    ("Canal", before.channel.mention, True),
                ],
            )
            await self._send_log(member.guild, "voice_activity", e)
        elif before.channel and after.channel and before.channel != after.channel:
            e = embed(
                title="🔀 Schimbat canalul vocal",
                color=0xF39C12,
                fields=[
                    ("Utilizator", f"{member.mention}", True),
                    ("De la", before.channel.mention, True),
                    ("La", after.channel.mention, True),
                ],
            )
            await self._send_log(member.guild, "voice_activity", e)

    # ─── Reacții pe mesaje ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if payload.user_id == self.bot.user.id:
            return
        member = guild.get_member(payload.user_id)
        if member and member.bot:
            return
        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        emoji_str = str(payload.emoji)
        e = embed(
            title="➕ Reacție adăugată",
            color=config.COLOR_INFO,
            fields=[
                ("Utilizator", f"{member.mention if member else payload.user_id}", True),
                ("Emoji", emoji_str, True),
                ("Canal", channel.mention, True),
                ("Mesaj", f"[Sari la mesaj]({message.jump_url})", False),
            ],
        )
        await self._send_log(guild, "msg_edit", e)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        emoji_str = str(payload.emoji)
        e = embed(
            title="➖ Reacție ștearsă",
            color=config.COLOR_WARNING,
            fields=[
                ("Utilizator", f"{member.mention if member else payload.user_id}", True),
                ("Emoji", emoji_str, True),
                ("Canal", channel.mention, True),
                ("Mesaj", f"[Sari la mesaj]({message.jump_url})", False),
            ],
        )
        await self._send_log(guild, "msg_edit", e)

    # ─── Log comenzi slash ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command,
    ):
        if not interaction.guild:
            return
        user = interaction.user
        channel = interaction.channel
        e = embed(
            title="📘 Comandă folosită",
            color=config.COLOR_INFO,
            fields=[
                ("Comandă", f"/{command.qualified_name}", True),
                ("Utilizator", f"{user.mention} (`{user.id}`)", True),
                ("Canal", channel.mention if channel else "DM", True),
            ],
        )
        await self._send_log(interaction.guild, "role_update", e)


async def setup(bot):
    await bot.add_cog(EventLog(bot))
=======
import discord
from discord.ext import commands
from discord import app_commands, AuditLogAction
from datetime import datetime, timezone

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed


LOG_CHANNELS_MAP = {
    "msg_delete":      "🗑️ Mesaje şterse",
    "msg_edit":        "✏️ Mesaje editate",
    "member_join":     "📥 Membri join",
    "member_leave":    "📤 Membri leave",
    "member_ban":      "🔨 Banuri",
    "member_unban":    "✅ Debanuri",
    "role_update":     "🎭 Roluri",
    "voice_activity":  "🔊 Voce",
    "nickname_change": "📛 Nickname",
    "invite_track":    "🔗 Invite",
}

AUTO_CHANNELS = {
    "msg_delete":     "log-mesaje",
    "msg_edit":       "log-mesaje",
    "member_join":    "log-membri",
    "member_leave":   "log-membri",
    "member_ban":     "log-moderare",
    "member_unban":   "log-moderare",
    "role_update":    "log-server",
    "voice_activity": "log-voice",
    "nickname_change":"log-membri",
    "invite_track":   "log-membri",
}

# Categoria preferată pentru loguri (dacă există deja pe server)
LOG_CATEGORY_ID = 1452797800088866970


class EventLog(commands.Cog, name="Logging"):
    """Sistem avansat de logging al evenimentelor."""

    def __init__(self, bot):
        self.bot = bot
        self._invite_cache: dict[int, dict[str, int]] = {}

    async def _get_logs_category(self, guild: discord.Guild) -> discord.CategoryChannel | None:
        """Returnează categoria în care se vor crea canalele de log.

        1) Încearcă categoria cu ID-ul fixat (LOG_CATEGORY_ID).
        2) Dacă nu există sau nu e categorie, folosește/creează „📋 GDP Logs”.
        """
        category = guild.get_channel(LOG_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = discord.utils.get(guild.categories, name="📋 GDP Logs")
            if not category:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                }
                # Rolurile cu administrator au acces la loguri
                for role in guild.roles:
                    if role.permissions.administrator:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=True)
                category = await guild.create_category("📋 GDP Logs", overwrites=overwrites)
        return category

    async def _auto_setup_logging_for_guild(self, guild: discord.Guild):
        """Se asigură că toate canalele de log există pentru un guild.

        Este idempotent: dacă există deja canalele, doar actualizează ID-urile în DB.
        """
        category = await self._get_logs_category(guild)
        if category is None:
            return

        channels_config = {
            "log-mesaje":    ["msg_delete", "msg_edit"],
            "log-membri":    ["member_join", "member_leave", "nickname_change", "invite_track"],
            "log-moderare":  ["member_ban", "member_unban"],
            "log-voice":     ["voice_activity"],
            "log-server":    ["role_update"],
        }

        for ch_name, log_types in channels_config.items():
            ch = discord.utils.get(category.text_channels, name=ch_name)
            if not ch:
                ch = await guild.create_text_channel(ch_name, category=category)
            for lt in log_types:
                await db.set_log_channel(guild.id, lt, ch.id)

    async def _send_log(self, guild: discord.Guild, log_type: str, embed_data: discord.Embed):
        channels = await db.get_log_channels(guild.id)
        ch_id = channels.get(log_type, 0)
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if ch:
            try:
                await ch.send(embed=embed_data)
            except Exception:
                pass

    # ─── Auto-setup la pornirea botului ───────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        # La pornire / reconectare, ne asigurăm că fiecare guild are canalele de log
        for guild in self.bot.guilds:
            try:
                await self._auto_setup_logging_for_guild(guild)
            except Exception:
                # Nu blocăm on_ready dacă un guild dă eroare
                continue

    @app_commands.command(name="setlogchannel2", description="[Admin] Setează manual un canal de log")
    @app_commands.describe(
        log_type="Tipul de log (msg_delete/msg_edit/member_join/etc.)",
        channel="Canalul de log"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel_manual(self, interaction: discord.Interaction,
                                      log_type: str, channel: discord.TextChannel):
        if log_type not in LOG_CHANNELS_MAP:
            types = ", ".join(f"`{k}`" for k in LOG_CHANNELS_MAP)
            return await interaction.response.send_message(
                embed=error_embed(f"Tip invalid. Tipuri disponibile:\n{types}"), ephemeral=True
            )
        await db.set_log_channel(interaction.guild.id, log_type, channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Log `{log_type}` → {channel.mention}.")
        )

    @app_commands.command(name="logstatus", description="[Admin] Afişează canalele de log configurate")
    @app_commands.checks.has_permissions(administrator=True)
    async def log_status(self, interaction: discord.Interaction):
        channels = await db.get_log_channels(interaction.guild.id)
        lines = []
        for key, label in LOG_CHANNELS_MAP.items():
            ch_id = channels.get(key, 0)
            ch = interaction.guild.get_channel(ch_id) if ch_id else None
            status = ch.mention if ch else "❌ Nesetat"
            lines.append(f"{label}: {status}")
        await interaction.response.send_message(embed=embed(
            title="📋 Status Logging",
            description="\n".join(lines),
            color=config.COLOR_PRIMARY
        ), ephemeral=True)

    # ─── Message delete ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        e = embed(
            title="🗑️ Mesaj şters",
            color=config.COLOR_ERROR,
            fields=[
                ("Autor", f"{message.author.mention} (`{message.author.id}`)", True),
                ("Canal", message.channel.mention, True),
                ("Conținut", f"```{message.content[:900] or 'fără text'}```", False),
            ],
        )
        e.set_thumbnail(url=message.author.display_avatar.url)
        if message.attachments:
            e.add_field(name="Fişiere", value="\n".join(a.filename for a in message.attachments), inline=False)
        await self._send_log(message.guild, "msg_delete", e)

    # ─── Message edit ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return
        e = embed(
            title="✏️ Mesaj editat",
            color=config.COLOR_WARNING,
            fields=[
                ("Autor", f"{before.author.mention} (`{before.author.id}`)", True),
                ("Canal", before.channel.mention, True),
                ("Link", f"[Sari la mesaj]({after.jump_url})", True),
                ("Înainte", f"```{before.content[:450] or 'gol'}```", False),
                ("După", f"```{after.content[:450] or 'gol'}```", False),
            ],
        )
        e.set_thumbnail(url=before.author.display_avatar.url)
        await self._send_log(before.guild, "msg_edit", e)

    # ─── Member join ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        account_age = (datetime.now(timezone.utc) - member.created_at).days
        suspicious = account_age < 7
        e = embed(
            title="📥 Membru nou",
            color=config.COLOR_SUCCESS if not suspicious else config.COLOR_WARNING,
            fields=[
                ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                ("Tag", str(member), True),
                ("Cont creat", f"<t:{int(member.created_at.timestamp())}:R> ({account_age}z)", True),
                ("Membri totali", str(member.guild.member_count), True),
                ("⚠️ Cont nou", "DA — verificați!" if suspicious else "Nu", True),
            ],
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, "member_join", e)

    # ─── Member leave ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        e = embed(
            title="📤 Membru plecat",
            color=config.COLOR_ERROR,
            fields=[
                ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                ("Tag", str(member), True),
                ("Roluri", " ".join(roles[:8]) or "Niciunul", False),
            ],
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await self._send_log(member.guild, "member_leave", e)

    # ─── Ban / Unban ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        responsible = "necunoscut"
        try:
            async for entry in guild.audit_logs(limit=5, action=AuditLogAction.ban):
                if entry.target.id == user.id:
                    responsible = f"{entry.user.mention} (`{entry.user.id}`)"
                    break
        except discord.Forbidden:
            responsible = "necunoscut (fără permisiune la audit log)"

        e = embed(
            title="🔨 Utilizator banat",
            color=config.COLOR_ERROR,
            fields=[
                ("Utilizator", f"{user.mention} (`{user.id}`)", True),
                ("Responsabil", responsible, True),
                ("Tag", str(user), True),
            ],
        )
        e.set_thumbnail(url=user.display_avatar.url)
        await self._send_log(guild, "member_ban", e)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        responsible = "necunoscut"
        try:
            async for entry in guild.audit_logs(limit=5, action=AuditLogAction.unban):
                if entry.target.id == user.id:
                    responsible = f"{entry.user.mention} (`{entry.user.id}`)"
                    break
        except discord.Forbidden:
            responsible = "necunoscut (fără permisiune la audit log)"

        e = embed(
            title="✅ Utilizator debanat",
            color=config.COLOR_SUCCESS,
            fields=[
                ("Utilizator", f"{user.mention} (`{user.id}`)", True),
                ("Responsabil", responsible, True),
            ],
        )
        await self._send_log(guild, "member_unban", e)

    # ─── Nickname change ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick and before.roles == after.roles:
            return

        if before.nick != after.nick:
            e = embed(
                title="📛 Nickname schimbat",
                color=config.COLOR_INFO,
                fields=[
                    ("Utilizator", f"{after.mention} (`{after.id}`)", True),
                    ("Înainte", before.nick or before.name, True),
                    ("După", after.nick or after.name, True),
                ],
            )
            e.set_thumbnail(url=after.display_avatar.url)
            await self._send_log(after.guild, "nickname_change", e)

        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            if not added and not removed:
                return
            fields = [("Utilizator", f"{after.mention} (`{after.id}`)", True)]
            if added:
                fields.append(("Roluri adăugate", " ".join(r.mention for r in added), False))
            if removed:
                fields.append(("Roluri eliminate", " ".join(r.mention for r in removed), False))

            responsible = "necunoscut"
            try:
                async for entry in after.guild.audit_logs(limit=5, action=AuditLogAction.member_role_update):
                    if entry.target.id == after.id:
                        responsible = f"{entry.user.mention} (`{entry.user.id}`)"
                        break
            except discord.Forbidden:
                responsible = "necunoscut (fără permisiune la audit log)"

            fields.append(("Responsabil", responsible, False))
            e = embed(title="🎭 Roluri modificate", color=config.COLOR_INFO, fields=fields)
            e.set_thumbnail(url=after.display_avatar.url)
            await self._send_log(after.guild, "role_update", e)

    # ─── Voice activity ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                     before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        if before.channel == after.channel:
            return

        if after.channel and not before.channel:
            e = embed(
                title="🔊 Intrat în voice",
                color=0x2ECC71,
                fields=[
                    ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                    ("Canal", after.channel.mention, True),
                ],
            )
            await self._send_log(member.guild, "voice_activity", e)
        elif before.channel and not after.channel:
            e = embed(
                title="🔇 Ieşit din voice",
                color=0xE74C3C,
                fields=[
                    ("Utilizator", f"{member.mention} (`{member.id}`)", True),
                    ("Canal", before.channel.mention, True),
                ],
            )
            await self._send_log(member.guild, "voice_activity", e)
        elif before.channel and after.channel and before.channel != after.channel:
            e = embed(
                title="🔀 Schimbat canalul vocal",
                color=0xF39C12,
                fields=[
                    ("Utilizator", f"{member.mention}", True),
                    ("De la", before.channel.mention, True),
                    ("La", after.channel.mention, True),
                ],
            )
            await self._send_log(member.guild, "voice_activity", e)

    # ─── Reacții pe mesaje ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if payload.user_id == self.bot.user.id:
            return
        member = guild.get_member(payload.user_id)
        if member and member.bot:
            return
        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        emoji_str = str(payload.emoji)
        e = embed(
            title="➕ Reacție adăugată",
            color=config.COLOR_INFO,
            fields=[
                ("Utilizator", f"{member.mention if member else payload.user_id}", True),
                ("Emoji", emoji_str, True),
                ("Canal", channel.mention, True),
                ("Mesaj", f"[Sari la mesaj]({message.jump_url})", False),
            ],
        )
        await self._send_log(guild, "msg_edit", e)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        emoji_str = str(payload.emoji)
        e = embed(
            title="➖ Reacție ștearsă",
            color=config.COLOR_WARNING,
            fields=[
                ("Utilizator", f"{member.mention if member else payload.user_id}", True),
                ("Emoji", emoji_str, True),
                ("Canal", channel.mention, True),
                ("Mesaj", f"[Sari la mesaj]({message.jump_url})", False),
            ],
        )
        await self._send_log(guild, "msg_edit", e)

    # ─── Log comenzi slash ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command,
    ):
        if not interaction.guild:
            return
        user = interaction.user
        channel = interaction.channel
        e = embed(
            title="📘 Comandă folosită",
            color=config.COLOR_INFO,
            fields=[
                ("Comandă", f"/{command.qualified_name}", True),
                ("Utilizator", f"{user.mention} (`{user.id}`)", True),
                ("Canal", channel.mention if channel else "DM", True),
            ],
        )
        await self._send_log(interaction.guild, "role_update", e)


async def setup(bot):
    await bot.add_cog(EventLog(bot))
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
