<<<<<<< HEAD
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from discord.ext import tasks

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed

MONTHS_RO = {
    1: "Ianuarie", 2: "Februarie", 3: "Martie", 4: "Aprilie",
    5: "Mai", 6: "Iunie", 7: "Iulie", 8: "August",
    9: "Septembrie", 10: "Octombrie", 11: "Noiembrie", 12: "Decembrie"
}

BIRTHDAY_REWARD = 500   # coins cadou de ziua de naştere


class Birthday(commands.Cog, name="Birthday"):
    """Sistem de zile de naştere."""

    def __init__(self, bot):
        self.bot = bot
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    bday_group = app_commands.Group(name="birthday", description="Sistem zile de naştere")

    # ─── /birthday set ───────────────────────────────────────────────────────

    @bday_group.command(name="set", description="Înregistrează-ți ziua de naştere")
    @app_commands.describe(day="Ziua (1-31)", month="Luna (1-12)", year="Anul naşterii (opțional)")
    async def set_birthday(self, interaction: discord.Interaction,
                            day: int, month: int, year: int = None):
        if not 1 <= day <= 31:
            return await interaction.response.send_message(
                embed=error_embed("Ziua trebuie să fie între 1 și 31."), ephemeral=True
            )
        if not 1 <= month <= 12:
            return await interaction.response.send_message(
                embed=error_embed("Luna trebuie să fie între 1 și 12."), ephemeral=True
            )
        if year and not 1900 <= year <= datetime.now().year - 5:
            return await interaction.response.send_message(
                embed=error_embed("Anul naşterii nu este valid."), ephemeral=True
            )
        # Validate day/month combo
        try:
            datetime(year or 2000, month, day)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed(f"Data {day}/{month} nu este validă."), ephemeral=True
            )

        await db.set_birthday(interaction.user.id, interaction.guild.id, day, month, year)

        age_str = ""
        if year:
            age = datetime.now().year - year
            age_str = f"\n**Vârstă:** {age} ani"

        await interaction.response.send_message(
            embed=embed(
                title="🎂 Zi de naştere înregistrată!",
                description=(
                    f"Data ta de naştere a fost setată la "
                    f"**{day} {MONTHS_RO[month]}**{' ' + str(year) if year else ''}!{age_str}\n\n"
                    f"Vei fi felicitat automat în ziua ta! 🎉"
                ),
                color=0xFF69B4
            ),
            ephemeral=True
        )

    # ─── /birthday remove ────────────────────────────────────────────────────

    @bday_group.command(name="remove", description="Elimină-ți ziua de naştere înregistrată")
    async def remove_birthday(self, interaction: discord.Interaction):
        bday = await db.get_birthday(interaction.user.id, interaction.guild.id)
        if not bday:
            return await interaction.response.send_message(
                embed=error_embed("Nu ai o zi de naştere înregistrată."), ephemeral=True
            )
        import aiosqlite
        from utils.database import DB_PATH
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "DELETE FROM birthdays WHERE user_id=? AND guild_id=?",
                (interaction.user.id, interaction.guild.id)
            )
            await conn.commit()
        await interaction.response.send_message(
            embed=success_embed("Ziua ta de naştere a fost eliminată."), ephemeral=True
        )

    # ─── /birthday check ─────────────────────────────────────────────────────

    @bday_group.command(name="check", description="Afișează ziua de naştere a unui utilizator")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def birthday_check(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        bday = await db.get_birthday(target.id, interaction.guild.id)
        if not bday:
            return await interaction.response.send_message(
                embed=embed(
                    title="🎂 Zi de naştere",
                    description=f"{target.mention} nu are o zi de naştere înregistrată.",
                    color=0xFF69B4
                )
            )
        now = datetime.now(timezone.utc)
        next_bday = datetime(now.year, bday["month"], bday["day"], tzinfo=timezone.utc)
        if next_bday < now:
            next_bday = next_bday.replace(year=now.year + 1)
        days_left = (next_bday - now).days

        age_str = ""
        if bday.get("birth_year"):
            age = now.year - bday["birth_year"]
            age_str = f"\n**Vârstă:** {age} ani"

        await interaction.response.send_message(embed=embed(
            title=f"🎂 Ziua de naştere — {target.display_name}",
            description=(
                f"**Data:** {bday['day']} {MONTHS_RO[bday['month']]}{age_str}\n"
                f"**Zile până la ziua de naştere:** {days_left} zile 🎉"
            ),
            color=0xFF69B4,
            thumbnail=target.display_avatar.url
        ))

    # ─── /birthday list ──────────────────────────────────────────────────────

    @bday_group.command(name="list", description="Afișează zilele de naştere viitoare")
    async def birthdays_list(self, interaction: discord.Interaction):
        bdays = await db.get_upcoming_birthdays(interaction.guild.id, 15)
        if not bdays:
            return await interaction.response.send_message(
                embed=embed(
                    title="🎂 Zile de naştere",
                    description="Niciun membru nu şi-a înregistrat ziua de naştere.",
                    color=0xFF69B4
                )
            )
        now = datetime.now(timezone.utc)
        # Sort by days until birthday
        def days_until(b):
            try:
                nd = datetime(now.year, b["month"], b["day"], tzinfo=timezone.utc)
                if nd < now:
                    nd = nd.replace(year=now.year + 1)
                return (nd - now).days
            except Exception:
                return 999
        bdays.sort(key=days_until)

        lines = []
        for b in bdays:
            member = interaction.guild.get_member(b["user_id"])
            name = member.display_name if member else f"ID:{b['user_id']}"
            days = days_until(b)
            today = days == 0
            prefix = "🎂 **AZI!**" if today else f"📅 **{days}** zile"
            lines.append(f"{prefix} — {name} ({b['day']} {MONTHS_RO[b['month']]})")

        await interaction.response.send_message(embed=embed(
            title="🎂 Zile de naştere viitoare",
            description="\n".join(lines),
            color=0xFF69B4
        ))

    # ─── /birthday setchannel ────────────────────────────────────────────────

    @bday_group.command(name="setchannel", description="[Admin] Setează canalul de anunțuri birthday")
    @app_commands.describe(channel="Canalul")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_birthday_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "birthday_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal birthday setat la {channel.mention}.")
        )

    # ─── Daily birthday check task ───────────────────────────────────────────

    @tasks.loop(hours=1)
    async def check_birthdays(self):
        now = datetime.now(timezone.utc)
        if now.hour != 9:   # Check at 9:00 UTC every day
            return

        today_str = now.strftime("%Y-%m-%d")

        for guild in self.bot.guilds:
            bdays = await db.get_todays_birthdays(guild.id, now.day, now.month)
            if not bdays:
                continue

            settings = await db.get_guild_settings(guild.id)
            ch_id = settings.get("birthday_channel") or 0
            ch = guild.get_channel(ch_id) if ch_id else None

            for bday in bdays:
                if bday.get("last_wished") == today_str:
                    continue

                member = guild.get_member(bday["user_id"])
                if not member:
                    continue

                age_str = ""
                if bday.get("birth_year"):
                    age = now.year - bday["birth_year"]
                    age_str = f" Te felicităm pentru **{age} ani**!"

                # Give birthday coins
                await db.update_balance(member.id, guild.id, BIRTHDAY_REWARD)
                await db.update_last_wished(member.id, guild.id, today_str)

                e = embed(
                    title="🎂 La mulți ani!",
                    description=(
                        f"Astăzi este ziua de naştere a {member.mention}! 🎉🎊\n"
                        f"{age_str}\n\n"
                        f"**Cadou:** {BIRTHDAY_REWARD} 🪙 coins!\n"
                        f"Serverul îți urează **La mulți ani**! 🎈"
                    ),
                    color=0xFF69B4,
                    thumbnail=member.display_avatar.url
                )

                if ch:
                    await ch.send(content=member.mention, embed=e)
                else:
                    try:
                        await member.send(embed=embed(
                            title="🎂 La mulți ani!",
                            description=(
                                f"**{guild.name}** îți urează **La mulți ani**!{age_str}\n"
                                f"**Cadou:** {BIRTHDAY_REWARD} 🪙 coins!"
                            ),
                            color=0xFF69B4
                        ))
                    except discord.Forbidden:
                        pass

    @check_birthdays.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Birthday(bot))
=======
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from discord.ext import tasks

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed

MONTHS_RO = {
    1: "Ianuarie", 2: "Februarie", 3: "Martie", 4: "Aprilie",
    5: "Mai", 6: "Iunie", 7: "Iulie", 8: "August",
    9: "Septembrie", 10: "Octombrie", 11: "Noiembrie", 12: "Decembrie"
}

BIRTHDAY_REWARD = 500   # coins cadou de ziua de naştere


class Birthday(commands.Cog, name="Birthday"):
    """Sistem de zile de naştere."""

    def __init__(self, bot):
        self.bot = bot
        self.check_birthdays.start()

    def cog_unload(self):
        self.check_birthdays.cancel()

    bday_group = app_commands.Group(name="birthday", description="Sistem zile de naştere")

    # ─── /birthday set ───────────────────────────────────────────────────────

    @bday_group.command(name="set", description="Înregistrează-ți ziua de naştere")
    @app_commands.describe(day="Ziua (1-31)", month="Luna (1-12)", year="Anul naşterii (opțional)")
    async def set_birthday(self, interaction: discord.Interaction,
                            day: int, month: int, year: int = None):
        if not 1 <= day <= 31:
            return await interaction.response.send_message(
                embed=error_embed("Ziua trebuie să fie între 1 și 31."), ephemeral=True
            )
        if not 1 <= month <= 12:
            return await interaction.response.send_message(
                embed=error_embed("Luna trebuie să fie între 1 și 12."), ephemeral=True
            )
        if year and not 1900 <= year <= datetime.now().year - 5:
            return await interaction.response.send_message(
                embed=error_embed("Anul naşterii nu este valid."), ephemeral=True
            )
        # Validate day/month combo
        try:
            datetime(year or 2000, month, day)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed(f"Data {day}/{month} nu este validă."), ephemeral=True
            )

        await db.set_birthday(interaction.user.id, interaction.guild.id, day, month, year)

        age_str = ""
        if year:
            age = datetime.now().year - year
            age_str = f"\n**Vârstă:** {age} ani"

        await interaction.response.send_message(
            embed=embed(
                title="🎂 Zi de naştere înregistrată!",
                description=(
                    f"Data ta de naştere a fost setată la "
                    f"**{day} {MONTHS_RO[month]}**{' ' + str(year) if year else ''}!{age_str}\n\n"
                    f"Vei fi felicitat automat în ziua ta! 🎉"
                ),
                color=0xFF69B4
            ),
            ephemeral=True
        )

    # ─── /birthday remove ────────────────────────────────────────────────────

    @bday_group.command(name="remove", description="Elimină-ți ziua de naştere înregistrată")
    async def remove_birthday(self, interaction: discord.Interaction):
        bday = await db.get_birthday(interaction.user.id, interaction.guild.id)
        if not bday:
            return await interaction.response.send_message(
                embed=error_embed("Nu ai o zi de naştere înregistrată."), ephemeral=True
            )
        import aiosqlite
        from utils.database import DB_PATH
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "DELETE FROM birthdays WHERE user_id=? AND guild_id=?",
                (interaction.user.id, interaction.guild.id)
            )
            await conn.commit()
        await interaction.response.send_message(
            embed=success_embed("Ziua ta de naştere a fost eliminată."), ephemeral=True
        )

    # ─── /birthday check ─────────────────────────────────────────────────────

    @bday_group.command(name="check", description="Afișează ziua de naştere a unui utilizator")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def birthday_check(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        bday = await db.get_birthday(target.id, interaction.guild.id)
        if not bday:
            return await interaction.response.send_message(
                embed=embed(
                    title="🎂 Zi de naştere",
                    description=f"{target.mention} nu are o zi de naştere înregistrată.",
                    color=0xFF69B4
                )
            )
        now = datetime.now(timezone.utc)
        next_bday = datetime(now.year, bday["month"], bday["day"], tzinfo=timezone.utc)
        if next_bday < now:
            next_bday = next_bday.replace(year=now.year + 1)
        days_left = (next_bday - now).days

        age_str = ""
        if bday.get("birth_year"):
            age = now.year - bday["birth_year"]
            age_str = f"\n**Vârstă:** {age} ani"

        await interaction.response.send_message(embed=embed(
            title=f"🎂 Ziua de naştere — {target.display_name}",
            description=(
                f"**Data:** {bday['day']} {MONTHS_RO[bday['month']]}{age_str}\n"
                f"**Zile până la ziua de naştere:** {days_left} zile 🎉"
            ),
            color=0xFF69B4,
            thumbnail=target.display_avatar.url
        ))

    # ─── /birthday list ──────────────────────────────────────────────────────

    @bday_group.command(name="list", description="Afișează zilele de naştere viitoare")
    async def birthdays_list(self, interaction: discord.Interaction):
        bdays = await db.get_upcoming_birthdays(interaction.guild.id, 15)
        if not bdays:
            return await interaction.response.send_message(
                embed=embed(
                    title="🎂 Zile de naştere",
                    description="Niciun membru nu şi-a înregistrat ziua de naştere.",
                    color=0xFF69B4
                )
            )
        now = datetime.now(timezone.utc)
        # Sort by days until birthday
        def days_until(b):
            try:
                nd = datetime(now.year, b["month"], b["day"], tzinfo=timezone.utc)
                if nd < now:
                    nd = nd.replace(year=now.year + 1)
                return (nd - now).days
            except Exception:
                return 999
        bdays.sort(key=days_until)

        lines = []
        for b in bdays:
            member = interaction.guild.get_member(b["user_id"])
            name = member.display_name if member else f"ID:{b['user_id']}"
            days = days_until(b)
            today = days == 0
            prefix = "🎂 **AZI!**" if today else f"📅 **{days}** zile"
            lines.append(f"{prefix} — {name} ({b['day']} {MONTHS_RO[b['month']]})")

        await interaction.response.send_message(embed=embed(
            title="🎂 Zile de naştere viitoare",
            description="\n".join(lines),
            color=0xFF69B4
        ))

    # ─── /birthday setchannel ────────────────────────────────────────────────

    @bday_group.command(name="setchannel", description="[Admin] Setează canalul de anunțuri birthday")
    @app_commands.describe(channel="Canalul")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_birthday_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "birthday_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal birthday setat la {channel.mention}.")
        )

    # ─── Daily birthday check task ───────────────────────────────────────────

    @tasks.loop(hours=1)
    async def check_birthdays(self):
        now = datetime.now(timezone.utc)
        if now.hour != 9:   # Check at 9:00 UTC every day
            return

        today_str = now.strftime("%Y-%m-%d")

        for guild in self.bot.guilds:
            bdays = await db.get_todays_birthdays(guild.id, now.day, now.month)
            if not bdays:
                continue

            settings = await db.get_guild_settings(guild.id)
            ch_id = settings.get("birthday_channel") or 0
            ch = guild.get_channel(ch_id) if ch_id else None

            for bday in bdays:
                if bday.get("last_wished") == today_str:
                    continue

                member = guild.get_member(bday["user_id"])
                if not member:
                    continue

                age_str = ""
                if bday.get("birth_year"):
                    age = now.year - bday["birth_year"]
                    age_str = f" Te felicităm pentru **{age} ani**!"

                # Give birthday coins
                await db.update_balance(member.id, guild.id, BIRTHDAY_REWARD)
                await db.update_last_wished(member.id, guild.id, today_str)

                e = embed(
                    title="🎂 La mulți ani!",
                    description=(
                        f"Astăzi este ziua de naştere a {member.mention}! 🎉🎊\n"
                        f"{age_str}\n\n"
                        f"**Cadou:** {BIRTHDAY_REWARD} 🪙 coins!\n"
                        f"Serverul îți urează **La mulți ani**! 🎈"
                    ),
                    color=0xFF69B4,
                    thumbnail=member.display_avatar.url
                )

                if ch:
                    await ch.send(content=member.mention, embed=e)
                else:
                    try:
                        await member.send(embed=embed(
                            title="🎂 La mulți ani!",
                            description=(
                                f"**{guild.name}** îți urează **La mulți ani**!{age_str}\n"
                                f"**Cadou:** {BIRTHDAY_REWARD} 🪙 coins!"
                            ),
                            color=0xFF69B4
                        ))
                    except discord.Forbidden:
                        pass

    @check_birthdays.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Birthday(bot))
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
