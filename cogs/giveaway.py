import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import random
import asyncio

import config
from utils import database as db
from utils.helpers import now_iso, parse_time, format_duration, embed, success_embed, error_embed

GIVEAWAY_EMOJI = "🎉"


class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Participă!", style=discord.ButtonStyle.success,
                       emoji="🎉", custom_id="giveaway_join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=embed(
                title="🎉 Participare înregistrată!",
                description="Ai intrat în giveaway! Mult noroc! 🍀",
                color=config.COLOR_SUCCESS
            ),
            ephemeral=True
        )
        # Add reaction programmatically as participation tracking
        await interaction.message.add_reaction(GIVEAWAY_EMOJI)


class Giveaway(commands.Cog, name="Giveaway"):
    """Sistem de giveaway-uri."""

    def __init__(self, bot):
        self.bot = bot
        self.check_giveaways.start()
        bot.add_view(GiveawayView())

    def cog_unload(self):
        self.check_giveaways.cancel()

    def build_giveaway_embed(self, prize: str, host: discord.Member, end_time: datetime,
                              winners: int, ended: bool = False, winner_mentions: list = None) -> discord.Embed:
        if ended:
            desc = (
                f"**Premiu:** {prize}\n"
                f"**Organizat de:** {host.mention}\n"
                f"**Câștigători:** {', '.join(winner_mentions) if winner_mentions else 'Niciun participant'}"
            )
            e = embed(title="🎊 Giveaway încheiat!", description=desc, color=config.COLOR_ERROR)
        else:
            time_left = end_time - datetime.now(timezone.utc)
            secs = max(0, int(time_left.total_seconds()))
            desc = (
                f"**Premiu:** {prize}\n"
                f"**Organizat de:** {host.mention}\n"
                f"**Câștigători:** {winners}\n"
                f"**Se termină:** <t:{int(end_time.timestamp())}:R>\n\n"
                f"Apasă butonul sau reacționează cu {GIVEAWAY_EMOJI} pentru a participa!"
            )
            e = embed(title=f"🎉 GIVEAWAY — {prize}", description=desc, color=config.COLOR_ECONOMY)
        e.set_footer(text=f"GDP Community • {'Încheiat' if ended else 'În desfășurare'}")
        return e

    @app_commands.command(name="giveaway", description="Pornește un giveaway")
    @app_commands.describe(
        duration="Durata (ex: 1h, 30m, 1d)",
        winners="Numărul de câștigători",
        prize="Premiul"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def start_giveaway(self, interaction: discord.Interaction,
                              duration: str, winners: int, prize: str):
        seconds = parse_time(duration)
        if seconds < 10:
            return await interaction.response.send_message(
                embed=error_embed("Durata minimă este de 10 secunde."), ephemeral=True
            )
        winners = max(1, min(winners, 20))
        end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)

        e = self.build_giveaway_embed(prize, interaction.user, end_time, winners)
        await interaction.response.send_message(embed=e, view=GiveawayView())
        msg = await interaction.original_response()
        await msg.add_reaction(GIVEAWAY_EMOJI)

        await db.create_giveaway(
            interaction.guild.id, interaction.channel.id, msg.id,
            interaction.user.id, prize, winners, end_time.isoformat()
        )

    @app_commands.command(name="endgiveaway", description="Termină imediat un giveaway după ID mesaj")
    @app_commands.describe(message_id="ID-ul mesajului giveaway-ului")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def end_giveaway_cmd(self, interaction: discord.Interaction, message_id: str):
        giveaways = await db.get_active_giveaways()
        giveaway = next((g for g in giveaways if str(g["message_id"]) == message_id), None)
        if not giveaway:
            return await interaction.response.send_message(
                embed=error_embed("Giveaway-ul nu a fost găsit sau este deja încheiat."), ephemeral=True
            )
        await self._finalize_giveaway(giveaway)
        await interaction.response.send_message(
            embed=success_embed("Giveaway-ul a fost încheiat!"), ephemeral=True
        )

    @app_commands.command(name="reroll", description="Alege noi câștigători pentru un giveaway")
    @app_commands.describe(message_id="ID-ul mesajului giveaway-ului")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, message_id: str):
        try:
            msg = await interaction.channel.fetch_message(int(message_id))
        except Exception:
            return await interaction.response.send_message(
                embed=error_embed("Mesajul nu a fost găsit în acest canal."), ephemeral=True
            )
        reaction = discord.utils.get(msg.reactions, emoji=GIVEAWAY_EMOJI)
        if not reaction:
            return await interaction.response.send_message(
                embed=error_embed("Nicio reacție găsită pe mesaj."), ephemeral=True
            )
        participants = [u async for u in reaction.users() if not u.bot]
        if not participants:
            return await interaction.response.send_message(
                embed=error_embed("Niciun participant!"), ephemeral=True
            )
        winner = random.choice(participants)
        await interaction.response.send_message(embed=embed(
            title="🎊 Reroll!",
            description=f"Noul câștigător este: {winner.mention}! Felicitări! 🎉",
            color=config.COLOR_ECONOMY
        ))

    async def _finalize_giveaway(self, giveaway: dict):
        guild = self.bot.get_guild(giveaway["guild_id"])
        if not guild:
            return
        channel = guild.get_channel(giveaway["channel_id"])
        if not channel:
            return
        try:
            message = await channel.fetch_message(giveaway["message_id"])
        except Exception:
            await db.end_giveaway(giveaway["id"])
            return

        reaction = discord.utils.get(message.reactions, emoji=GIVEAWAY_EMOJI)
        participants = []
        if reaction:
            participants = [u async for u in reaction.users() if not u.bot]

        host = guild.get_member(giveaway["host_id"]) or self.bot.get_user(giveaway["host_id"])
        end_time = datetime.fromisoformat(giveaway["end_time"])
        num_winners = min(giveaway["winners_count"], len(participants))
        winners = random.sample(participants, num_winners) if participants else []

        winner_mentions = [w.mention for w in winners]
        e = self.build_giveaway_embed(
            giveaway["prize"], host, end_time,
            giveaway["winners_count"], ended=True, winner_mentions=winner_mentions
        )
        await message.edit(embed=e, view=None)

        if winners:
            await channel.send(
                content=" ".join(winner_mentions),
                embed=embed(
                    title="🎊 Câștigătorii giveaway-ului!",
                    description=f"Premiu: **{giveaway['prize']}**\nFelicitări: {', '.join(winner_mentions)}! 🎉",
                    color=config.COLOR_ECONOMY
                )
            )
        else:
            await channel.send(embed=error_embed("Niciun participant la giveaway. Nu există câștigători."))

        await db.end_giveaway(giveaway["id"])

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        now = datetime.now(timezone.utc)
        giveaways = await db.get_active_giveaways()
        for g in giveaways:
            end = datetime.fromisoformat(g["end_time"])
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if now >= end:
                await self._finalize_giveaway(g)

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
