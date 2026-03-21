<<<<<<< HEAD
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import random

import config
from utils import database as db
from utils.helpers import now_iso, success_embed, error_embed, embed


COIN = "🪙"


class Economy(commands.Cog, name="Economie"):
    """Sistem de economie cu coins, shop și recompense."""

    def __init__(self, bot):
        self.bot = bot

    # ─── /balance ────────────────────────────────────────────────────────────

    @app_commands.command(name="balance", description="Afișează balanța ta sau a altui utilizator")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        data = await db.get_economy(target.id, interaction.guild.id)
        total = data["balance"] + data["bank"]
        e = embed(
            title=f"{COIN} Portofel — {target.display_name}",
            color=config.COLOR_ECONOMY,
            fields=[
                (f"{COIN} Cash", f"**{data['balance']:,}** coins", True),
                ("🏦 Bancă", f"**{data['bank']:,}** coins", True),
                ("💰 Total", f"**{total:,}** coins", True),
            ],
        )
        e.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=e)

    # ─── /daily ──────────────────────────────────────────────────────────────

    @app_commands.command(name="daily", description=f"Primește recompensa zilnică de {config.DAILY_COINS} coins")
    async def daily(self, interaction: discord.Interaction):
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        now = datetime.now(timezone.utc)
        if data["last_daily"]:
            last = datetime.fromisoformat(data["last_daily"])
            diff = now - last
            if diff < timedelta(hours=24):
                remaining = timedelta(hours=24) - diff
                h, rem = divmod(int(remaining.total_seconds()), 3600)
                m = rem // 60
                return await interaction.response.send_message(
                    embed=error_embed(f"Ai primit deja recompensa azi!\nRevino în **{h}h {m}m**."),
                    ephemeral=True
                )
        reward = config.DAILY_COINS
        await db.update_balance(interaction.user.id, interaction.guild.id, reward)
        await db.set_last_daily(interaction.user.id, interaction.guild.id, now.isoformat())
        new_data = await db.get_economy(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed(
            title=f"{COIN} Recompensă zilnică!",
            description=f"Ai primit **{reward:,}** coins!\n{COIN} Balanță: **{new_data['balance']:,}** coins",
            color=config.COLOR_ECONOMY
        ))

    # ─── /work ───────────────────────────────────────────────────────────────

    @app_commands.command(name="work", description="Muncește pentru a câștiga coins (cooldown 1h)")
    async def work(self, interaction: discord.Interaction):
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        now = datetime.now(timezone.utc)
        if data["last_work"]:
            last = datetime.fromisoformat(data["last_work"])
            diff = now - last
            if diff < timedelta(hours=1):
                remaining = timedelta(hours=1) - diff
                m = int(remaining.total_seconds() // 60)
                return await interaction.response.send_message(
                    embed=error_embed(f"Ești obosit! Revino în **{m}m**."), ephemeral=True
                )
        jobs = [
            ("programator", "ai codat o aplicație"),
            ("streamer", "ai făcut un stream de gaming"),
            ("designer", "ai creat un logo"),
            ("moderator", "ai moderat serverul"),
            ("trader", "ai făcut tranzacții"),
            ("chef", "ai gătit mâncăruri delicioase"),
            ("mecanic", "ai reparat mașini"),
        ]
        job, desc = random.choice(jobs)
        earned = random.randint(config.WORK_MIN, config.WORK_MAX)
        await db.update_balance(interaction.user.id, interaction.guild.id, earned)
        await db.set_last_work(interaction.user.id, interaction.guild.id, now.isoformat())
        await interaction.response.send_message(embed=embed(
            title=f"💼 Ai muncit ca {job}!",
            description=f"Ai {desc} și ai câștigat **{earned:,}** {COIN} coins!",
            color=config.COLOR_ECONOMY
        ))

    # ─── /transfer ───────────────────────────────────────────────────────────

    @app_commands.command(name="transfer", description="Transferă coins unui alt utilizator")
    @app_commands.describe(member="Destinatarul", amount="Suma de transferat")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("Nu te poți transfera ție însuți."), ephemeral=True
            )
        if amount <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Suma trebuie să fie pozitivă."), ephemeral=True
            )
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < amount:
            return await interaction.response.send_message(
                embed=error_embed(f"Balanță insuficientă! Ai **{data['balance']:,}** coins."),
                ephemeral=True
            )
        await db.transfer_coins(interaction.user.id, interaction.guild.id, member.id, amount)
        await interaction.response.send_message(embed=success_embed(
            f"Ai transferat **{amount:,}** {COIN} coins lui {member.mention}!"
        ))

    # ─── /rob ────────────────────────────────────────────────────────────────

    @app_commands.command(name="rob", description="Încearcă să furi coins de la cineva (risc!)")
    @app_commands.describe(member="Victima")
    async def rob(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("Nu te poți jefui pe tine însuți."), ephemeral=True
            )
        victim_data = await db.get_economy(member.id, interaction.guild.id)
        robber_data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if victim_data["balance"] < 50:
            return await interaction.response.send_message(
                embed=error_embed(f"{member.mention} este prea sărac, nu merită!"), ephemeral=True
            )
        success = random.random() < 0.40
        if success:
            stolen = random.randint(1, min(victim_data["balance"] // 2, 500))
            await db.transfer_coins(member.id, interaction.guild.id, interaction.user.id, stolen)
            await interaction.response.send_message(embed=embed(
                title="🦹 Jaf reușit!",
                description=f"Ai furat **{stolen:,}** {COIN} coins de la {member.mention}!",
                color=config.COLOR_SUCCESS
            ))
        else:
            fine = random.randint(50, 200)
            fine = min(fine, robber_data["balance"])
            await db.transfer_coins(interaction.user.id, interaction.guild.id, member.id, fine)
            await interaction.response.send_message(embed=embed(
                title="🚔 Prins la furat!",
                description=f"Ai fost prins și ai plătit o amendă de **{fine:,}** {COIN} coins!",
                color=config.COLOR_ERROR
            ))

    # ─── /leaderboard (economy) ──────────────────────────────────────────────

    @app_commands.command(name="richest", description="Top 10 cei mai bogați membri")
    async def richest(self, interaction: discord.Interaction):
        lb = await db.get_economy_leaderboard(interaction.guild.id)
        if not lb:
            return await interaction.response.send_message(
                embed=error_embed("Nu există date economice încă."), ephemeral=True
            )
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(lb):
            user = interaction.guild.get_member(row["user_id"])
            name = user.display_name if user else f"ID:{row['user_id']}"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — {row['total']:,} {COIN}")
        await interaction.response.send_message(embed=embed(
            title="💰 Top Bogați — GDP Community",
            description="\n".join(lines),
            color=config.COLOR_ECONOMY
        ))

    # ─── /shop ───────────────────────────────────────────────────────────────

    @app_commands.command(name="shop", description="Afișează magazinul serverului")
    async def shop(self, interaction: discord.Interaction):
        fields = [
            (f"{v['name']}", f"💰 {v['price']:,} coins\n_{v['description']}_", True)
            for k, v in config.SHOP_ITEMS.items()
        ]
        e = embed(
            title="🛒 Magazin GDP Community",
            description="Cumpără iteme cu `/buy <item>`",
            color=config.COLOR_ECONOMY,
            fields=fields
        )
        await interaction.response.send_message(embed=e)

    # ─── /buy ────────────────────────────────────────────────────────────────

    @app_commands.command(name="buy", description="Cumpără un item din shop")
    @app_commands.describe(item="Cheia itemului (ex: lootbox)")
    async def buy(self, interaction: discord.Interaction, item: str):
        item = item.lower()
        if item not in config.SHOP_ITEMS:
            keys = ", ".join(f"`{k}`" for k in config.SHOP_ITEMS)
            return await interaction.response.send_message(
                embed=error_embed(f"Item inexistent. Iteme disponibile: {keys}"), ephemeral=True
            )
        shop_item = config.SHOP_ITEMS[item]
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < shop_item["price"]:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Balanță insuficientă!\nNecesar: **{shop_item['price']:,}** coins | "
                    f"Tu ai: **{data['balance']:,}** coins"
                ), ephemeral=True
            )
        await db.update_balance(interaction.user.id, interaction.guild.id, -shop_item["price"])
        await db.add_to_inventory(interaction.user.id, interaction.guild.id, item)
        if item == "lootbox":
            reward = random.choice([50, 100, 200, 500, 1000, 2000])
            await db.update_balance(interaction.user.id, interaction.guild.id, reward)
            return await interaction.response.send_message(embed=embed(
                title="📦 Loot Box deschis!",
                description=f"Ai câștigat **{reward:,}** {COIN} coins din loot box!",
                color=config.COLOR_ECONOMY
            ))
        await interaction.response.send_message(embed=success_embed(
            f"Ai cumpărat **{shop_item['name']}** pentru **{shop_item['price']:,}** {COIN} coins!"
        ))

    # ─── /inventory ──────────────────────────────────────────────────────────

    @app_commands.command(name="inventory", description="Afișează inventarul tău")
    async def inventory(self, interaction: discord.Interaction):
        items = await db.get_inventory(interaction.user.id, interaction.guild.id)
        if not items:
            return await interaction.response.send_message(
                embed=embed(title="🎒 Inventar gol", description="Nu ai niciun item.", color=config.COLOR_ECONOMY)
            )
        lines = []
        for row in items:
            shop = config.SHOP_ITEMS.get(row["item_key"])
            name = shop["name"] if shop else row["item_key"]
            lines.append(f"• **{name}** × {row['quantity']}")
        await interaction.response.send_message(embed=embed(
            title=f"🎒 Inventarul lui {interaction.user.display_name}",
            description="\n".join(lines),
            color=config.COLOR_ECONOMY
        ))

    # ─── /coinflip ───────────────────────────────────────────────────────────

    @app_commands.command(name="coinflip", description="Pariază coins pe cap sau pajură")
    @app_commands.describe(bet="Suma pariată", choice="cap sau pajura")
    async def coinflip(self, interaction: discord.Interaction, bet: int, choice: str):
        choice = choice.lower()
        if choice not in ("cap", "pajura"):
            return await interaction.response.send_message(
                embed=error_embed("Alege `cap` sau `pajura`."), ephemeral=True
            )
        if bet <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Pariul trebuie să fie pozitiv."), ephemeral=True
            )
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < bet:
            return await interaction.response.send_message(
                embed=error_embed(f"Balanță insuficientă! Ai **{data['balance']:,}** coins."), ephemeral=True
            )
        result = random.choice(["cap", "pajura"])
        won = result == choice
        change = bet if won else -bet
        await db.update_balance(interaction.user.id, interaction.guild.id, change)
        new_bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
        await interaction.response.send_message(embed=embed(
            title=f"{'🪙 Ai câștigat!' if won else '😢 Ai pierdut!'}",
            description=(
                f"Moneda a picat pe **{result}**.\n"
                f"{'Câștig' if won else 'Pierdere'}: **{bet:,}** coins\n"
                f"Balanță nouă: **{new_bal:,}** coins"
            ),
            color=config.COLOR_SUCCESS if won else config.COLOR_ERROR
        ))


async def setup(bot):
    await bot.add_cog(Economy(bot))
=======
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import random

import config
from utils import database as db
from utils.helpers import now_iso, success_embed, error_embed, embed


COIN = "🪙"


class Economy(commands.Cog, name="Economie"):
    """Sistem de economie cu coins, shop și recompense."""

    def __init__(self, bot):
        self.bot = bot

    # ─── /balance ────────────────────────────────────────────────────────────

    @app_commands.command(name="balance", description="Afișează balanța ta sau a altui utilizator")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        data = await db.get_economy(target.id, interaction.guild.id)
        total = data["balance"] + data["bank"]
        e = embed(
            title=f"{COIN} Portofel — {target.display_name}",
            color=config.COLOR_ECONOMY,
            fields=[
                (f"{COIN} Cash", f"**{data['balance']:,}** coins", True),
                ("🏦 Bancă", f"**{data['bank']:,}** coins", True),
                ("💰 Total", f"**{total:,}** coins", True),
            ],
        )
        e.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=e)

    # ─── /daily ──────────────────────────────────────────────────────────────

    @app_commands.command(name="daily", description=f"Primește recompensa zilnică de {config.DAILY_COINS} coins")
    async def daily(self, interaction: discord.Interaction):
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        now = datetime.now(timezone.utc)
        if data["last_daily"]:
            last = datetime.fromisoformat(data["last_daily"])
            diff = now - last
            if diff < timedelta(hours=24):
                remaining = timedelta(hours=24) - diff
                h, rem = divmod(int(remaining.total_seconds()), 3600)
                m = rem // 60
                return await interaction.response.send_message(
                    embed=error_embed(f"Ai primit deja recompensa azi!\nRevino în **{h}h {m}m**."),
                    ephemeral=True
                )
        reward = config.DAILY_COINS
        await db.update_balance(interaction.user.id, interaction.guild.id, reward)
        await db.set_last_daily(interaction.user.id, interaction.guild.id, now.isoformat())
        new_data = await db.get_economy(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed(
            title=f"{COIN} Recompensă zilnică!",
            description=f"Ai primit **{reward:,}** coins!\n{COIN} Balanță: **{new_data['balance']:,}** coins",
            color=config.COLOR_ECONOMY
        ))

    # ─── /work ───────────────────────────────────────────────────────────────

    @app_commands.command(name="work", description="Muncește pentru a câștiga coins (cooldown 1h)")
    async def work(self, interaction: discord.Interaction):
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        now = datetime.now(timezone.utc)
        if data["last_work"]:
            last = datetime.fromisoformat(data["last_work"])
            diff = now - last
            if diff < timedelta(hours=1):
                remaining = timedelta(hours=1) - diff
                m = int(remaining.total_seconds() // 60)
                return await interaction.response.send_message(
                    embed=error_embed(f"Ești obosit! Revino în **{m}m**."), ephemeral=True
                )
        jobs = [
            ("programator", "ai codat o aplicație"),
            ("streamer", "ai făcut un stream de gaming"),
            ("designer", "ai creat un logo"),
            ("moderator", "ai moderat serverul"),
            ("trader", "ai făcut tranzacții"),
            ("chef", "ai gătit mâncăruri delicioase"),
            ("mecanic", "ai reparat mașini"),
        ]
        job, desc = random.choice(jobs)
        earned = random.randint(config.WORK_MIN, config.WORK_MAX)
        await db.update_balance(interaction.user.id, interaction.guild.id, earned)
        await db.set_last_work(interaction.user.id, interaction.guild.id, now.isoformat())
        await interaction.response.send_message(embed=embed(
            title=f"💼 Ai muncit ca {job}!",
            description=f"Ai {desc} și ai câștigat **{earned:,}** {COIN} coins!",
            color=config.COLOR_ECONOMY
        ))

    # ─── /transfer ───────────────────────────────────────────────────────────

    @app_commands.command(name="transfer", description="Transferă coins unui alt utilizator")
    @app_commands.describe(member="Destinatarul", amount="Suma de transferat")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("Nu te poți transfera ție însuți."), ephemeral=True
            )
        if amount <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Suma trebuie să fie pozitivă."), ephemeral=True
            )
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < amount:
            return await interaction.response.send_message(
                embed=error_embed(f"Balanță insuficientă! Ai **{data['balance']:,}** coins."),
                ephemeral=True
            )
        await db.transfer_coins(interaction.user.id, interaction.guild.id, member.id, amount)
        await interaction.response.send_message(embed=success_embed(
            f"Ai transferat **{amount:,}** {COIN} coins lui {member.mention}!"
        ))

    # ─── /rob ────────────────────────────────────────────────────────────────

    @app_commands.command(name="rob", description="Încearcă să furi coins de la cineva (risc!)")
    @app_commands.describe(member="Victima")
    async def rob(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("Nu te poți jefui pe tine însuți."), ephemeral=True
            )
        victim_data = await db.get_economy(member.id, interaction.guild.id)
        robber_data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if victim_data["balance"] < 50:
            return await interaction.response.send_message(
                embed=error_embed(f"{member.mention} este prea sărac, nu merită!"), ephemeral=True
            )
        success = random.random() < 0.40
        if success:
            stolen = random.randint(1, min(victim_data["balance"] // 2, 500))
            await db.transfer_coins(member.id, interaction.guild.id, interaction.user.id, stolen)
            await interaction.response.send_message(embed=embed(
                title="🦹 Jaf reușit!",
                description=f"Ai furat **{stolen:,}** {COIN} coins de la {member.mention}!",
                color=config.COLOR_SUCCESS
            ))
        else:
            fine = random.randint(50, 200)
            fine = min(fine, robber_data["balance"])
            await db.transfer_coins(interaction.user.id, interaction.guild.id, member.id, fine)
            await interaction.response.send_message(embed=embed(
                title="🚔 Prins la furat!",
                description=f"Ai fost prins și ai plătit o amendă de **{fine:,}** {COIN} coins!",
                color=config.COLOR_ERROR
            ))

    # ─── /leaderboard (economy) ──────────────────────────────────────────────

    @app_commands.command(name="richest", description="Top 10 cei mai bogați membri")
    async def richest(self, interaction: discord.Interaction):
        lb = await db.get_economy_leaderboard(interaction.guild.id)
        if not lb:
            return await interaction.response.send_message(
                embed=error_embed("Nu există date economice încă."), ephemeral=True
            )
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(lb):
            user = interaction.guild.get_member(row["user_id"])
            name = user.display_name if user else f"ID:{row['user_id']}"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — {row['total']:,} {COIN}")
        await interaction.response.send_message(embed=embed(
            title="💰 Top Bogați — GDP Community",
            description="\n".join(lines),
            color=config.COLOR_ECONOMY
        ))

    # ─── /shop ───────────────────────────────────────────────────────────────

    @app_commands.command(name="shop", description="Afișează magazinul serverului")
    async def shop(self, interaction: discord.Interaction):
        fields = [
            (f"{v['name']}", f"💰 {v['price']:,} coins\n_{v['description']}_", True)
            for k, v in config.SHOP_ITEMS.items()
        ]
        e = embed(
            title="🛒 Magazin GDP Community",
            description="Cumpără iteme cu `/buy <item>`",
            color=config.COLOR_ECONOMY,
            fields=fields
        )
        await interaction.response.send_message(embed=e)

    # ─── /buy ────────────────────────────────────────────────────────────────

    @app_commands.command(name="buy", description="Cumpără un item din shop")
    @app_commands.describe(item="Cheia itemului (ex: lootbox)")
    async def buy(self, interaction: discord.Interaction, item: str):
        item = item.lower()
        if item not in config.SHOP_ITEMS:
            keys = ", ".join(f"`{k}`" for k in config.SHOP_ITEMS)
            return await interaction.response.send_message(
                embed=error_embed(f"Item inexistent. Iteme disponibile: {keys}"), ephemeral=True
            )
        shop_item = config.SHOP_ITEMS[item]
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < shop_item["price"]:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Balanță insuficientă!\nNecesar: **{shop_item['price']:,}** coins | "
                    f"Tu ai: **{data['balance']:,}** coins"
                ), ephemeral=True
            )
        await db.update_balance(interaction.user.id, interaction.guild.id, -shop_item["price"])
        await db.add_to_inventory(interaction.user.id, interaction.guild.id, item)
        if item == "lootbox":
            reward = random.choice([50, 100, 200, 500, 1000, 2000])
            await db.update_balance(interaction.user.id, interaction.guild.id, reward)
            return await interaction.response.send_message(embed=embed(
                title="📦 Loot Box deschis!",
                description=f"Ai câștigat **{reward:,}** {COIN} coins din loot box!",
                color=config.COLOR_ECONOMY
            ))
        await interaction.response.send_message(embed=success_embed(
            f"Ai cumpărat **{shop_item['name']}** pentru **{shop_item['price']:,}** {COIN} coins!"
        ))

    # ─── /inventory ──────────────────────────────────────────────────────────

    @app_commands.command(name="inventory", description="Afișează inventarul tău")
    async def inventory(self, interaction: discord.Interaction):
        items = await db.get_inventory(interaction.user.id, interaction.guild.id)
        if not items:
            return await interaction.response.send_message(
                embed=embed(title="🎒 Inventar gol", description="Nu ai niciun item.", color=config.COLOR_ECONOMY)
            )
        lines = []
        for row in items:
            shop = config.SHOP_ITEMS.get(row["item_key"])
            name = shop["name"] if shop else row["item_key"]
            lines.append(f"• **{name}** × {row['quantity']}")
        await interaction.response.send_message(embed=embed(
            title=f"🎒 Inventarul lui {interaction.user.display_name}",
            description="\n".join(lines),
            color=config.COLOR_ECONOMY
        ))

    # ─── /coinflip ───────────────────────────────────────────────────────────

    @app_commands.command(name="coinflip", description="Pariază coins pe cap sau pajură")
    @app_commands.describe(bet="Suma pariată", choice="cap sau pajura")
    async def coinflip(self, interaction: discord.Interaction, bet: int, choice: str):
        choice = choice.lower()
        if choice not in ("cap", "pajura"):
            return await interaction.response.send_message(
                embed=error_embed("Alege `cap` sau `pajura`."), ephemeral=True
            )
        if bet <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Pariul trebuie să fie pozitiv."), ephemeral=True
            )
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < bet:
            return await interaction.response.send_message(
                embed=error_embed(f"Balanță insuficientă! Ai **{data['balance']:,}** coins."), ephemeral=True
            )
        result = random.choice(["cap", "pajura"])
        won = result == choice
        change = bet if won else -bet
        await db.update_balance(interaction.user.id, interaction.guild.id, change)
        new_bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
        await interaction.response.send_message(embed=embed(
            title=f"{'🪙 Ai câștigat!' if won else '😢 Ai pierdut!'}",
            description=(
                f"Moneda a picat pe **{result}**.\n"
                f"{'Câștig' if won else 'Pierdere'}: **{bet:,}** coins\n"
                f"Balanță nouă: **{new_bal:,}** coins"
            ),
            color=config.COLOR_SUCCESS if won else config.COLOR_ERROR
        ))


async def setup(bot):
    await bot.add_cog(Economy(bot))
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
