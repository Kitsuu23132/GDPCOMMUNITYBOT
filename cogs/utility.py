import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import platform
import time

import config
from utils.helpers import embed, info_embed


class Utility(commands.Cog, name="Utilitar"):
    """Comenzi utile pentru toți membrii."""

    def __init__(self, bot):
        self.bot = bot
        self._start_time = time.time()

    # ─── /help ───────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="Afișează lista de comenzi disponibile")
    async def help_cmd(self, interaction: discord.Interaction):
        e = embed(
            title="📖 GDP Community Bot — Ajutor",
            description="Folosește `/` pentru a accesa toate comenzile slash.",
            color=config.COLOR_PRIMARY,
            thumbnail=self.bot.user.display_avatar.url if self.bot.user else None,
            fields=[
                ("⚔️ Moderare", "`/ban` `/kick` `/mute` `/warn` `/purge` `/lock` `/slowmode`", False),
                ("⭐ Nivele", "`/rank` `/leaderboard`", False),
                ("🎫 Tickete", "`/ticket` `/closeticket` `/adduser`", False),
                ("🎊 Giveaway", "`/giveaway` `/endgiveaway` `/reroll`", False),
                ("ℹ️ Utilitar", "`/help` `/serverinfo` `/userinfo` `/botinfo` `/ping`", False),
                ("⚙️ Admin", "`/announce` `/embed` `/setwelcome` `/setlog` `/schedule add`", False),
            ]
        )
        await interaction.response.send_message(embed=e)

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
        uptime_secs = int(time.time() - self._start_time)
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
