import random
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from discord import app_commands

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed


class _SafeFormat(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class Tips(commands.Cog, name="Tips"):
    """Sfaturi automate trimise periodic intr-un canal."""

    tips = app_commands.Group(name="tips", description="Sfaturi automate in chat (admin)")

    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        self.tips_loop.cancel()

    async def _format_message(self, guild: discord.Guild, template: str) -> str:
        gs = await db.get_guild_settings(guild.id)
        sug_id = int(gs.get("suggestion_channel") or 0)
        if sug_id:
            ch = guild.get_channel(sug_id)
            suggestion_channel = ch.mention if ch else f"<#{sug_id}>"
        else:
            suggestion_channel = "canalul de sugestii"

        def mention_or(uid: int, fallback: str) -> str:
            if uid:
                return f"<@{uid}>"
            return f"@{fallback}" if fallback else "contributorii"

        credit_discord = mention_or(
            int(getattr(config, "TIP_CREDIT_DISCORD_USER_ID", 0) or 0),
            getattr(config, "TIP_CREDIT_DISCORD_FALLBACK", "") or "",
        )
        credit_logo = mention_or(
            int(getattr(config, "TIP_CREDIT_LOGO_USER_ID", 0) or 0),
            getattr(config, "TIP_CREDIT_LOGO_FALLBACK", "") or "",
        )
        rules = (
            f"[Regulament]({config.RULES_URL})" if getattr(config, "RULES_URL", "") else "#📃┃ʀᴇɢᴜʟɪ"
        )
        invite = (
            f"[link invite]({config.INVITE_URL})"
            if getattr(config, "INVITE_URL", "")
            else "cere staff-ului un invite"
        )
        currency = getattr(config, "CURRENCY_NAME", "PufuCoins")
        prefix = getattr(config, "PREFIX", "!")

        return template.format_map(
            _SafeFormat(
                suggestion_channel=suggestion_channel,
                credit_discord=credit_discord,
                credit_logo=credit_logo,
                rules=rules,
                invite=invite,
                currency=currency,
                prefix=prefix,
            )
        )

    @tasks.loop(minutes=1)
    async def tips_loop(self):
        if not self.bot.is_ready():
            return
        now = datetime.now(timezone.utc)
        messages = getattr(config, "TIPS_MESSAGES", None) or []
        if not messages:
            return
        for guild in self.bot.guilds:
            try:
                s = await db.get_tips_settings(guild.id)
                if not s.get("enabled") or not int(s.get("channel_id") or 0):
                    continue
                interval = max(15, int(s.get("interval_minutes") or config.TIPS_INTERVAL_MINUTES))
                last = s.get("last_sent_at")
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                    except ValueError:
                        last_dt = None
                    if last_dt and (now - last_dt).total_seconds() < interval * 60:
                        continue
                ch = guild.get_channel(int(s["channel_id"]))
                if not isinstance(ch, discord.TextChannel):
                    continue
                tpl = random.choice(messages)
                body = await self._format_message(guild, tpl)
                await ch.send(
                    embed=embed(
                        title="💡 Sfat GDP",
                        description=body,
                        color=config.COLOR_INFO,
                        footer="Sfat automat",
                    )
                )
                await db.update_tips_field(guild.id, "last_sent_at", now.isoformat())
            except Exception:
                continue

    @tips_loop.before_loop
    async def before_tips_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.tips_loop.is_running():
            self.tips_loop.start()

    @tips.command(name="setup", description="[Admin] Canalul unde se trimit sfaturile")
    @app_commands.describe(channel="Canal text")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tips_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_tips_field(interaction.guild.id, "channel_id", channel.id)
        await db.update_tips_field(interaction.guild.id, "enabled", 1)
        await interaction.response.send_message(
            embed=success_embed(f"Sfaturile automate vor fi trimise in {channel.mention}."),
            ephemeral=True,
        )

    @tips.command(name="disable", description="[Admin] Opreste sfaturile automate")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tips_disable(self, interaction: discord.Interaction):
        await db.update_tips_field(interaction.guild.id, "enabled", 0)
        await interaction.response.send_message(embed=success_embed("Sfaturi dezactivate."), ephemeral=True)

    @tips.command(name="enable", description="[Admin] Porneste sfaturile (necesita canal setat)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tips_enable(self, interaction: discord.Interaction):
        s = await db.get_tips_settings(interaction.guild.id)
        if not int(s.get("channel_id") or 0):
            return await interaction.response.send_message(
                embed=error_embed("Seteaza mai intai canalul cu `/tips setup`."),
                ephemeral=True,
            )
        await db.update_tips_field(interaction.guild.id, "enabled", 1)
        await interaction.response.send_message(embed=success_embed("Sfaturi activate."), ephemeral=True)

    @tips.command(name="interval", description="[Admin] Minute intre doua sfaturi (15–1440)")
    @app_commands.describe(minutes="Interval in minute")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tips_interval(
        self, interaction: discord.Interaction, minutes: app_commands.Range[int, 15, 1440]
    ):
        await db.update_tips_field(interaction.guild.id, "interval_minutes", int(minutes))
        await interaction.response.send_message(
            embed=success_embed(f"Interval setat la **{minutes}** minute."), ephemeral=True
        )

    @tips.command(name="test", description="[Admin] Preview un sfat in privat")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tips_test(self, interaction: discord.Interaction):
        messages = getattr(config, "TIPS_MESSAGES", None) or []
        if not messages:
            return await interaction.response.send_message(
                embed=error_embed("Nu exista mesaje in TIPS_MESSAGES (config.py)."), ephemeral=True
            )
        tpl = random.choice(messages)
        body = await self._format_message(interaction.guild, tpl)
        await interaction.response.send_message(
            embed=embed(title="💡 Sfat (test)", description=body, color=config.COLOR_INFO),
            ephemeral=True,
        )

    @tips.command(name="status", description="[Admin] Status sfaturi automate")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def tips_status(self, interaction: discord.Interaction):
        s = await db.get_tips_settings(interaction.guild.id)
        ch = interaction.guild.get_channel(int(s.get("channel_id") or 0))
        last = s.get("last_sent_at") or "n/a"
        await interaction.response.send_message(
            embed=embed(
                title="💡 Tips — status",
                color=config.COLOR_INFO,
                fields=[
                    ("Activ", "Da" if s.get("enabled") else "Nu", True),
                    ("Canal", ch.mention if ch else "lipseste", True),
                    (
                        "Interval (min)",
                        str(int(s.get("interval_minutes") or config.TIPS_INTERVAL_MINUTES)),
                        True,
                    ),
                    ("Ultima trimitere", last, False),
                    ("Mesaje in config", str(len(getattr(config, "TIPS_MESSAGES", []) or [])), True),
                ],
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Tips(bot))
