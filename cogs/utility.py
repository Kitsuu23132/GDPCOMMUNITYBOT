import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import platform
import time

import config
from utils.helpers import embed, info_embed, success_embed


class PollModal(discord.ui.Modal, title="📊 Sondaj"):
    def __init__(self):
        super().__init__(timeout=300)
        self.q = discord.ui.TextInput(
            label="Întrebare",
            placeholder="Ce vrei să întrebi comunitatea?",
            max_length=256,
            required=True,
        )
        self.o1 = discord.ui.TextInput(
            label="Opțiunea 1",
            placeholder="Prima variantă",
            max_length=80,
            required=True,
        )
        self.o2 = discord.ui.TextInput(
            label="Opțiunea 2",
            placeholder="A doua variantă",
            max_length=80,
            required=True,
        )
        self.o3 = discord.ui.TextInput(
            label="Opțiunea 3 (opțional)",
            placeholder="Lasă gol dacă nu ai nevoie",
            max_length=80,
            required=False,
        )
        self.o4 = discord.ui.TextInput(
            label="Opțiunea 4 (opțional)",
            placeholder="Lasă gol dacă nu ai nevoie",
            max_length=80,
            required=False,
        )
        self.add_item(self.q)
        self.add_item(self.o1)
        self.add_item(self.o2)
        self.add_item(self.o3)
        self.add_item(self.o4)

    async def on_submit(self, interaction: discord.Interaction):
        opts = [self.o1.value.strip(), self.o2.value.strip()]
        if self.o3.value.strip():
            opts.append(self.o3.value.strip())
        if self.o4.value.strip():
            opts.append(self.o4.value.strip())
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        lines = "\n".join(f"{emojis[i]} {opts[i]}" for i in range(len(opts)))
        e = embed(
            title=f"📊 {self.q.value}",
            description=f"{lines}\n\n*Votează cu reacțiile de mai jos.*",
            color=config.COLOR_PRIMARY,
            footer=f"Poll de {interaction.user.display_name}",
        )
        await interaction.response.send_message(embed=e)
        msg = await interaction.original_response()
        for i in range(len(opts)):
            await msg.add_reaction(emojis[i])


class HubPanelView(discord.ui.View):
    """Butoane rapide pentru comenzi frecvente (fără URL obligatoriu)."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ticket", style=discord.ButtonStyle.primary, custom_id="hub_ticket")
    async def btn_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed(
                title="🎫 Tickete",
                description="Folosește **/ticket** (admin) pentru panou sau panoul din canalul dedicat.",
                color=config.COLOR_INFO,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="💡 Sugestie", style=discord.ButtonStyle.success, custom_id="hub_suggest")
    async def btn_suggest(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed(
                title="💡 Sugestii",
                description="Scrie **/suggest** sau folosește butonul de pe panoul de sugestii.",
                color=config.COLOR_INFO,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="🚨 Raport", style=discord.ButtonStyle.danger, custom_id="hub_report")
    async def btn_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed(
                title="🚨 Raportare",
                description="Folosește comanda **/report** sau panoul de raportare din server.",
                color=config.COLOR_WARNING,
            ),
            ephemeral=True,
        )

    @discord.ui.button(label="🎵 Muzică", style=discord.ButtonStyle.secondary, custom_id="hub_music")
    async def btn_music(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed(
                title="🎵 Muzică",
                description="Intră într-un canal vocal și folosește **/play** + link sau numele melodiei.",
                color=config.COLOR_INFO,
            ),
            ephemeral=True,
        )


class Utility(commands.Cog, name="Utilitar"):
    """Comenzi utile pentru toți membrii."""

    def __init__(self, bot):
        self.bot = bot
        self._start_time = time.time()
        bot.add_view(HubPanelView())

    def _uptime_seconds(self) -> int:
        t0 = getattr(self.bot, "_start_time", self._start_time)
        return int(time.time() - t0)

    # ─── /help ───────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="Afișează lista de comenzi disponibile")
    async def help_cmd(self, interaction: discord.Interaction):
        e = embed(
            title="📖 GDP Community Bot — Ajutor",
            description="Folosește `/` pentru comenzi. Moneda serverului este **RDN** (economie).",
            color=config.COLOR_PRIMARY,
            thumbnail=self.bot.user.display_avatar.url if self.bot.user else None,
            fields=[
                ("⚔️ Moderare", "`/ban` `/kick` `/mute` `/warn` `/purge` `/lock` `/slowmode`", False),
                ("⭐ Nivele", "`/rank` `/leaderboard` `/setxp`", False),
                ("💎 Economie (RDN)", "`/daily` `/balance` `/shop` `/buy` `/givecoins` `/trade swap` `/minigame`", False),
                ("🎫 Tickete", "`/ticket` `/closeticket` `/adduser`", False),
                ("🎊 Giveaway", "`/giveaway` `/endgiveaway` `/reroll`", False),
                ("🎵 Muzică", "`/play` `/join` `/leave` `/queue` `/skip`", False),
                ("ℹ️ Utilitar", "`/help` `/status` `/poll` `/ping` `/serverinfo` `/userinfo` `/botinfo` `/snipe`", False),
                ("⚙️ Admin", "`/announce` `/embed` `/gdpanel` `/modcoins` `/setwelcome` `/setlog` `/schedule`", False),
            ]
        )
        await interaction.response.send_message(embed=e)

    # ─── /status ─────────────────────────────────────────────────────────────

    @app_commands.command(name="status", description="Stare bot: uptime, latență, bază de date")
    async def status_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uptime = self._uptime_seconds()
        h, rem = divmod(uptime, 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h}h {m}m {s}s"
        ws_ms = round(self.bot.latency * 1000)

        db_ok = "❓"
        try:
            from utils.database import DB_PATH
            import aiosqlite
            async with aiosqlite.connect(DB_PATH) as conn:
                await conn.execute("SELECT 1")
            db_ok = "✅ OK"
        except Exception as ex:
            db_ok = f"❌ {ex}"

        e = embed(
            title="🟢 GDP Bot — Status",
            color=config.COLOR_SUCCESS if ws_ms < 500 else config.COLOR_WARNING,
            fields=[
                ("⏱️ Uptime", uptime_str, True),
                ("🏓 Latență WS", f"{ws_ms} ms", True),
                ("🗄️ SQLite", db_ok, True),
                ("🐍 Python", platform.python_version(), True),
                ("📦 discord.py", discord.__version__, True),
                ("👥 Servere", str(len(self.bot.guilds)), True),
            ],
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    # ─── /poll ───────────────────────────────────────────────────────────────

    @app_commands.command(name="poll", description="Creează un sondaj cu reacții (formular)")
    async def poll_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PollModal())

    # ─── /gdpanel ────────────────────────────────────────────────────────────

    @app_commands.command(name="gdpanel", description="[Admin] Postează panoul rapid GDP (butoane)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gdpanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        lines = [
            "**GDP Community — hub rapid**",
            "",
            "• Apasă pe butoane pentru indicații.",
            "• Staff: `/ticket`, `/suggestionpanel`, `/report` pentru panouri.",
        ]
        if config.RULES_URL:
            lines.append(f"• [Regulament]({config.RULES_URL})")
        if config.INVITE_URL:
            lines.append(f"• [Invite server]({config.INVITE_URL})")
        e = embed(
            title="🏠 GDP Hub",
            description="\n".join(lines),
            color=config.COLOR_PRIMARY,
            thumbnail=interaction.guild.icon.url if interaction.guild.icon else None,
        )
        await interaction.channel.send(embed=e, view=HubPanelView())
        await interaction.followup.send(embed=success_embed("Panoul a fost postat în canal."), ephemeral=True)

    # ─── /ping ───────────────────────────────────────────────────────────────

    @app_commands.command(name="ping", description="Afișează latența botului")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        color = config.COLOR_SUCCESS if latency < 100 else (config.COLOR_WARNING if latency < 200 else config.COLOR_ERROR)
        await interaction.response.send_message(embed=embed(
            title="🏓 Pong!",
            description=f"Latență WebSocket: **{latency}ms**",
            color=color
        ))

    # ─── /botinfo ────────────────────────────────────────────────────────────

    @app_commands.command(name="botinfo", description="Informații despre bot")
    async def botinfo(self, interaction: discord.Interaction):
        uptime_secs = self._uptime_seconds()
        h, rem = divmod(uptime_secs, 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h}h {m}m {s}s"
        e = embed(
            title=f"🤖 {self.bot.user.name}",
            color=config.COLOR_PRIMARY,
            thumbnail=self.bot.user.display_avatar.url,
            fields=[
                ("👥 Servere", str(len(self.bot.guilds)), True),
                ("👤 Utilizatori", str(sum(g.member_count for g in self.bot.guilds)), True),
                ("⏱️ Uptime", uptime_str, True),
                ("🐍 Python", platform.python_version(), True),
                ("📦 discord.py", discord.__version__, True),
                ("🏓 Latență", f"{round(self.bot.latency * 1000)}ms", True),
            ]
        )
        await interaction.response.send_message(embed=e)

    # ─── /serverinfo ─────────────────────────────────────────────────────────

    @app_commands.command(name="serverinfo", description="Informații despre server")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots
        text_chs = len(guild.text_channels)
        voice_chs = len(guild.voice_channels)
        e = embed(
            title=f"🏰 {guild.name}",
            color=config.COLOR_PRIMARY,
            thumbnail=guild.icon.url if guild.icon else None,
            fields=[
                ("🆔 ID Server", str(guild.id), True),
                ("👑 Owner", guild.owner.mention if guild.owner else "N/A", True),
                ("📅 Creat", f"<t:{int(guild.created_at.timestamp())}:R>", True),
                ("👥 Membrii", f"**{humans}** umani | **{bots}** boți", True),
                ("📝 Canale text", str(text_chs), True),
                ("🔊 Canale vocale", str(voice_chs), True),
                ("🎭 Roluri", str(len(guild.roles)), True),
                ("😀 Emoji-uri", str(len(guild.emojis)), True),
                ("🔒 Verificare", str(guild.verification_level).capitalize(), True),
                ("✨ Boost Level", f"Tier {guild.premium_tier}", True),
                ("💎 Boosteri", str(guild.premium_subscription_count), True),
            ]
        )
        if guild.banner:
            e.set_image(url=guild.banner.url)
        await interaction.response.send_message(embed=e)

    # ─── /userinfo ───────────────────────────────────────────────────────────

    @app_commands.command(name="userinfo", description="Informații despre un utilizator")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        roles = [r.mention for r in reversed(target.roles) if r != interaction.guild.default_role]
        roles_str = " ".join(roles[:10]) + (f" +{len(roles)-10} mai mult" if len(roles) > 10 else "") if roles else "Niciun rol"
        e = embed(
            title=f"👤 {target.display_name}",
            color=target.color if target.color != discord.Color.default() else config.COLOR_PRIMARY,
            thumbnail=target.display_avatar.url,
            fields=[
                ("🆔 ID", str(target.id), True),
                ("📛 Tag", str(target), True),
                ("🤖 Bot", "Da" if target.bot else "Nu", True),
                ("📅 Account creat", f"<t:{int(target.created_at.timestamp())}:R>", True),
                ("📥 Joined", f"<t:{int(target.joined_at.timestamp())}:R>" if target.joined_at else "N/A", True),
                ("🎭 Roluri", roles_str, False),
            ]
        )
        await interaction.response.send_message(embed=e)

    # ─── /roleinfo ───────────────────────────────────────────────────────────

    @app_commands.command(name="roleinfo", description="Informații despre un rol")
    @app_commands.describe(role="Rolul")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        perms = [p for p, v in role.permissions if v]
        perms_str = ", ".join(perms[:8]) + ("..." if len(perms) > 8 else "") if perms else "Nicio permisiune specială"
        e = embed(
            title=f"🎭 {role.name}",
            color=role.color if role.color != discord.Color.default() else config.COLOR_PRIMARY,
            fields=[
                ("🆔 ID", str(role.id), True),
                ("🎨 Culoare", str(role.color), True),
                ("👥 Membrii", str(len(role.members)), True),
                ("📅 Creat", f"<t:{int(role.created_at.timestamp())}:R>", True),
                ("🔼 Poziție", str(role.position), True),
                ("🤖 Managed", "Da" if role.managed else "Nu", True),
                ("🔔 Mentionabil", "Da" if role.mentionable else "Nu", True),
                ("📌 Hoisted", "Da" if role.hoist else "Nu", True),
                ("🔑 Permisiuni principale", perms_str, False),
            ]
        )
        await interaction.response.send_message(embed=e)

    # ─── /snipe ──────────────────────────────────────────────────────────────

    _snipe_cache: dict = {}

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        self._snipe_cache[message.channel.id] = message

    @app_commands.command(name="snipe", description="Afișează ultimul mesaj șters din canal")
    async def snipe(self, interaction: discord.Interaction):
        msg = self._snipe_cache.get(interaction.channel.id)
        if not msg:
            return await interaction.response.send_message(
                embed=info_embed("Nu există mesaje șterse recent în acest canal."),
                ephemeral=True
            )
        e = embed(
            title="👻 Mesaj recuperat",
            description=msg.content or "*[Mesaj fără text]*",
            color=config.COLOR_WARNING,
            thumbnail=msg.author.display_avatar.url,
            fields=[
                ("Autor", msg.author.mention, True),
                ("Când", f"<t:{int(msg.created_at.timestamp())}:R>", True),
            ]
        )
        await interaction.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(Utility(bot))
