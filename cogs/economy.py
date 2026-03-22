import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import random

import config
from utils import database as db
from utils.helpers import success_embed, error_embed, embed


def _rdn() -> str:
    return getattr(config, "CURRENCY_NAME", "RDN")


async def interaction_is_bot_owner(interaction: discord.Interaction) -> bool:
    """Owner aplicație (Portal) sau ID-uri din BOT_OWNER_IDS."""
    uid = interaction.user.id
    if getattr(config, "BOT_OWNER_IDS", None) and uid in config.BOT_OWNER_IDS:
        return True
    app = await interaction.client.application_info()
    if app.owner and app.owner.id == uid:
        return True
    if app.team and app.team.owner_id == uid:
        return True
    return False


class Economy(commands.Cog, name="Economie"):
    """Sistem RDN: shop, daily, minigame-uri, trade, transfer între membri."""

    def __init__(self, bot):
        self.bot = bot

    def _shop_item_roles(self) -> dict:
        return getattr(config, "SHOP_ITEM_ROLES", {}) or {}

    async def _sync_shop_roles_from_inventory(
        self, member: discord.Member, guild: discord.Guild
    ) -> list[str]:
        """
        Pentru fiecare item din shop cu rol mapat: dacă ai cantitate > 0 în inventar → primești rolul;
        dacă nu mai ai itemul → ți se scoate rolul.
        """
        warnings: list[str] = []
        inv = await db.get_inventory(member.id, guild.id)
        have = {r["item_key"]: r["quantity"] for r in inv}
        for item_key, role_id in self._shop_item_roles().items():
            role = guild.get_role(role_id)
            if not role:
                warnings.append(f"⚠️ Rolul cu ID `{role_id}` (`{item_key}`) nu există pe server.")
                continue
            qty = have.get(item_key, 0)
            should_have = qty > 0
            has_role = role in member.roles
            try:
                if should_have and not has_role:
                    await member.add_roles(role, reason="GDP shop — item în inventar")
                elif not should_have and has_role:
                    await member.remove_roles(role, reason="GDP shop — item inexistent în inventar")
            except discord.Forbidden:
                warnings.append(
                    f"⚠️ Nu am permisiunea de a modifica rolul {role.mention} "
                    "(pune rolul botului **deasupra** rolului respectiv în setări)."
                )
            except discord.HTTPException as e:
                warnings.append(f"⚠️ Discord: {e}")
        return warnings

    # ─── Autocomplete shop ───────────────────────────────────────────────────

    async def _shop_keys_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        cur = current.lower()
        choices = []
        for k, v in config.SHOP_ITEMS.items():
            name = v["name"]
            if cur in k or cur in name.lower():
                choices.append(app_commands.Choice(name=f"{name} ({k})", value=k))
        return choices[:25]

    # ─── /balance ────────────────────────────────────────────────────────────

    @app_commands.command(name="balance", description="Afișează balanța ta sau a altui membru (RDN)")
    @app_commands.describe(member="Utilizatorul (opțional)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        data = await db.get_economy(target.id, interaction.guild.id)
        total = data["balance"] + data["bank"]
        c = _rdn()
        e = embed(
            title=f"💎 Portofel — {target.display_name}",
            color=config.COLOR_ECONOMY,
            fields=[
                (f"💵 {c} (cash)", f"**{data['balance']:,}**", True),
                ("🏦 Bancă", f"**{data['bank']:,}**", True),
                ("📊 Total", f"**{total:,}** {c}", True),
            ],
        )
        e.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=e)

    # ─── /daily ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="daily",
        description=f"Primește recompensa zilnică ({getattr(config, 'DAILY_COINS', 50)} {_rdn()})",
    )
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
                    ephemeral=True,
                )
        reward = config.DAILY_COINS
        await db.update_balance(interaction.user.id, interaction.guild.id, reward)
        await db.set_last_daily(interaction.user.id, interaction.guild.id, now.isoformat())
        new_data = await db.get_economy(interaction.user.id, interaction.guild.id)
        c = _rdn()
        await interaction.response.send_message(
            embed=embed(
                title=f"☀️ Daily {_rdn()}",
                description=(
                    f"Ai primit **{reward:,}** {c}!\n"
                    f"💵 Balanță: **{new_data['balance']:,}** {c}"
                ),
                color=config.COLOR_ECONOMY,
            )
        )

    # ─── /gaddcoins (owner) ──────────────────────────────────────────────────

    @app_commands.command(
        name="gaddcoins",
        description="[Owner bot] Adaugă sau scade RDN unui membru",
    )
    @app_commands.describe(member="Membrul", amount="Suma (pozitiv = adaugă, negativ = scade)")
    async def gaddcoins(
        self, interaction: discord.Interaction, member: discord.Member, amount: int
    ):
        if not await interaction_is_bot_owner(interaction):
            return await interaction.response.send_message(
                embed=error_embed("Doar **owner-ul botului** poate folosi această comandă."),
                ephemeral=True,
            )
        if amount == 0:
            return await interaction.response.send_message(
                embed=error_embed("Suma nu poate fi 0."), ephemeral=True
            )
        await db.update_balance(member.id, interaction.guild.id, amount)
        c = _rdn()
        act = "Adăugat" if amount > 0 else "Scăzut"
        await interaction.response.send_message(
            embed=success_embed(
                f"{act} **{abs(amount):,}** {c} {'lui' if amount > 0 else 'de la'} {member.mention}."
            )
        )

    async def _give_coins_user_to_user(
        self, interaction: discord.Interaction, member: discord.Member, amount: int
    ):
        if member == interaction.user:
            await interaction.response.send_message(
                embed=error_embed("Nu îți poți trimite ție însuți."), ephemeral=True
            )
            return
        if amount <= 0:
            await interaction.response.send_message(
                embed=error_embed("Suma trebuie să fie pozitivă."), ephemeral=True
            )
            return
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < amount:
            await interaction.response.send_message(
                embed=error_embed(
                    f"Balanță insuficientă! Ai **{data['balance']:,}** {_rdn()}."
                ),
                ephemeral=True,
            )
            return
        await db.transfer_coins(interaction.user.id, interaction.guild.id, member.id, amount)
        c = _rdn()
        await interaction.response.send_message(
            embed=success_embed(
                f"Ai trimis **{amount:,}** {c} lui {member.mention}!"
            )
        )

    # ─── /givecoins (între membri) ───────────────────────────────────────────

    @app_commands.command(
        name="givecoins",
        description=f"Trimite {_rdn()} din portofelul tău altui membru",
    )
    @app_commands.describe(member="Destinatarul", amount=f"Suma de {_rdn()}")
    async def givecoins(
        self, interaction: discord.Interaction, member: discord.Member, amount: int
    ):
        await self._give_coins_user_to_user(interaction, member, amount)

    # ─── /transfer (alias) ───────────────────────────────────────────────────

    @app_commands.command(
        name="transfer",
        description="Alias pentru /givecoins — transferă RDN",
    )
    @app_commands.describe(member="Destinatarul", amount="Suma")
    async def transfer(
        self, interaction: discord.Interaction, member: discord.Member, amount: int
    ):
        await self._give_coins_user_to_user(interaction, member, amount)

    # ─── Grup /trade ─────────────────────────────────────────────────────────

    trade = app_commands.Group(name="trade", description="Schimburi: item ↔ item (RDN)")

    @trade.command(name="swap", description="Schimbă un item din inventar cu altul din shop (plătești diferența)")
    @app_commands.describe(
        din_item="Itemul pe care îl ai acum (cheie, ex: vip_rank)",
        in_item="Itemul dorit (cheie, ex: veteran_rank)",
    )
    async def trade_swap(
        self, interaction: discord.Interaction, din_item: str, in_item: str
    ):
        din_item = din_item.lower().strip()
        in_item = in_item.lower().strip()
        if din_item == in_item:
            return await interaction.response.send_message(
                embed=error_embed("Alege două iteme diferite."), ephemeral=True
            )
        if din_item not in config.SHOP_ITEMS or in_item not in config.SHOP_ITEMS:
            return await interaction.response.send_message(
                embed=error_embed("Unul sau ambele iteme nu există în shop."), ephemeral=True
            )
        inv = await db.get_inventory(interaction.user.id, interaction.guild.id)
        have = {r["item_key"]: r["quantity"] for r in inv}
        if have.get(din_item, 0) < 1:
            return await interaction.response.send_message(
                embed=error_embed(f"Nu ai în inventar: `{din_item}`."), ephemeral=True
            )
        p_from = config.SHOP_ITEMS[din_item]["price"]
        p_to = config.SHOP_ITEMS[in_item]["price"]
        diff = p_to - p_from
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if diff > 0 and data["balance"] < diff:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Îți lipsesc **{diff - data['balance']:,}** {_rdn()} pentru diferență."
                ),
                ephemeral=True,
            )
        if diff > 0:
            await db.update_balance(interaction.user.id, interaction.guild.id, -diff)
        elif diff < 0:
            await db.update_balance(interaction.user.id, interaction.guild.id, -diff)
        ok = await db.remove_from_inventory(interaction.user.id, interaction.guild.id, din_item, 1)
        if not ok:
            if diff > 0:
                await db.update_balance(interaction.user.id, interaction.guild.id, diff)
            elif diff < 0:
                await db.update_balance(interaction.user.id, interaction.guild.id, diff)
            return await interaction.response.send_message(
                embed=error_embed("Eroare inventar."), ephemeral=True
            )
        await db.add_to_inventory(interaction.user.id, interaction.guild.id, in_item, 1)
        warn = await self._sync_shop_roles_from_inventory(
            interaction.user, interaction.guild
        )
        c = _rdn()
        n_from = config.SHOP_ITEMS[din_item]["name"]
        n_to = config.SHOP_ITEMS[in_item]["name"]
        extra = ""
        if diff > 0:
            extra = f"\nAi plătit **{diff:,}** {c} diferență."
        elif diff < 0:
            extra = f"\nȚi s-au returnat **{-diff:,}** {c}."
        msg = (
            f"Schimb: **{n_from}** → **{n_to}**.{extra}\n"
            "🎭 Rolurile legate de inventar au fost actualizate automat."
        )
        if warn:
            msg += "\n" + "\n".join(warn)
        await interaction.response.send_message(embed=success_embed(msg))

    @trade_swap.autocomplete("din_item")
    async def trade_swap_autocomplete_din(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._shop_keys_autocomplete(interaction, current)

    @trade_swap.autocomplete("in_item")
    async def trade_swap_autocomplete_in(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._shop_keys_autocomplete(interaction, current)

    # ─── Grup /minigame ──────────────────────────────────────────────────────

    minigame = app_commands.Group(
        name="minigame",
        description=f"Jocuri pentru {_rdn()} (max {config.MINIGAMES_PER_DAY}/zi)",
    )

    async def _run_minigame(
        self, interaction: discord.Interaction, title: str, description: str, base_reward: int
    ):
        allowed = await db.try_register_minigame_play(
            interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
        )
        if not allowed:
            rem = await db.get_minigames_remaining(
                interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
            )
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Ai folosit toate **{config.MINIGAMES_PER_DAY}** jocuri azi.\n"
                    f"Rămase: **{rem}** (reset zilnic UTC)."
                ),
                ephemeral=True,
            )
        await db.update_balance(interaction.user.id, interaction.guild.id, base_reward)
        bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
        left = await db.get_minigames_remaining(
            interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
        )
        c = _rdn()
        await interaction.response.send_message(
            embed=embed(
                title=title,
                description=(
                    f"{description}\n\n"
                    f"💰 **+{base_reward:,}** {c}\n"
                    f"💵 Balanță: **{bal:,}** {c}\n"
                    f"🎮 Mai ai **{left}** minigame-uri azi."
                ),
                color=config.COLOR_ECONOMY,
            )
        )

    @minigame.command(name="dice", description="Dă cu zarul — câștig aleator de RDN")
    async def mg_dice(self, interaction: discord.Interaction):
        a, b = random.randint(1, 6), random.randint(1, 6)
        s = a + b
        mult = 1.3 if s >= 9 else 1.0
        base = random.randint(config.MINIGAME_REWARD_MIN, config.MINIGAME_REWARD_MAX)
        reward = int(base * mult)
        desc = f"🎲 **{a}** + **{b}** = **{s}**"
        await self._run_minigame(interaction, "🎲 Dice", desc, reward)

    @minigame.command(name="guess", description="Ghicește numărul 1–10")
    @app_commands.describe(numar="Numărul tău (1-10)")
    async def mg_guess(self, interaction: discord.Interaction, numar: int):
        if not 1 <= numar <= 10:
            return await interaction.response.send_message(
                embed=error_embed("Alege un număr între **1** și **10**."), ephemeral=True
            )
        secret = random.randint(1, 10)
        base = random.randint(config.MINIGAME_REWARD_MIN, config.MINIGAME_REWARD_MAX)
        reward = int(base * (2.0 if numar == secret else 0.6))
        hit = "🎯 Ghicit!" if numar == secret else "❌ Nu a fost numărul."
        desc = f"{hit}\nNumăr: **{secret}**, tu: **{numar}**."
        allowed = await db.try_register_minigame_play(
            interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
        )
        if not allowed:
            rem = await db.get_minigames_remaining(
                interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
            )
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Limită zilnică atinsă. Rămase: **{rem}**."
                ),
                ephemeral=True,
            )
        await db.update_balance(interaction.user.id, interaction.guild.id, reward)
        bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
        left = await db.get_minigames_remaining(
            interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
        )
        c = _rdn()
        await interaction.response.send_message(
            embed=embed(
                title="🔢 Guess",
                description=(
                    f"{desc}\n\n"
                    f"💰 **+{reward:,}** {c}\n"
                    f"💵 Balanță: **{bal:,}** {c}\n"
                    f"🎮 Mai ai **{left}** minigame-uri azi."
                ),
                color=config.COLOR_ECONOMY,
            )
        )

    @minigame.command(name="slots", description="3 role — combinații bonus")
    async def mg_slots(self, interaction: discord.Interaction):
        syms = ["🍒", "🍋", "⭐", "💎", "7️⃣"]
        r = [random.choice(syms) for _ in range(3)]
        base = random.randint(config.MINIGAME_REWARD_MIN, config.MINIGAME_REWARD_MAX)
        if r[0] == r[1] == r[2]:
            reward = int(base * 2.5)
        elif r[0] == r[1] or r[1] == r[2]:
            reward = int(base * 1.4)
        else:
            reward = base
        desc = " | ".join(r)
        await self._run_minigame(interaction, "🎰 Slots", desc, reward)

    # ─── /work ───────────────────────────────────────────────────────────────

    @app_commands.command(name="work", description="Muncește pentru RDN (cooldown 1h)")
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
                    embed=error_embed(f"Revino la muncă în **{m}m**."), ephemeral=True
                )
        jobs = [
            ("programator", "ai codat ceva epic"),
            ("streamer", "ai făcut un stream"),
            ("designer", "ai creat un logo"),
            ("moderator", "ai moderat serverul"),
            ("trader", "ai făcut tranzacții"),
        ]
        job, desc = random.choice(jobs)
        earned = random.randint(config.WORK_MIN, config.WORK_MAX)
        await db.update_balance(interaction.user.id, interaction.guild.id, earned)
        await db.set_last_work(interaction.user.id, interaction.guild.id, now.isoformat())
        c = _rdn()
        await interaction.response.send_message(
            embed=embed(
                title=f"💼 {job}",
                description=f"{desc.capitalize()} — ai câștigat **{earned:,}** {c}!",
                color=config.COLOR_ECONOMY,
            )
        )

    # ─── /rob ────────────────────────────────────────────────────────────────

    @app_commands.command(name="rob", description="Încearcă să furi RDN (risc!)")
    @app_commands.describe(member="Ținta")
    async def rob(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("Nu te poți jefui singur."), ephemeral=True
            )
        victim_data = await db.get_economy(member.id, interaction.guild.id)
        robber_data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if victim_data["balance"] < 50:
            return await interaction.response.send_message(
                embed=error_embed(f"{member.mention} nu are destui {_rdn()}."), ephemeral=True
            )
        success = random.random() < 0.40
        c = _rdn()
        if success:
            stolen = random.randint(1, min(victim_data["balance"] // 2, 500))
            await db.transfer_coins(member.id, interaction.guild.id, interaction.user.id, stolen)
            await interaction.response.send_message(
                embed=embed(
                    title="🦹 Jaf reușit!",
                    description=f"Ai luat **{stolen:,}** {c} de la {member.mention}!",
                    color=config.COLOR_SUCCESS,
                )
            )
        else:
            fine = random.randint(50, 200)
            fine = min(fine, robber_data["balance"])
            await db.transfer_coins(interaction.user.id, interaction.guild.id, member.id, fine)
            await interaction.response.send_message(
                embed=embed(
                    title="🚔 Prins!",
                    description=f"Ai plătit **{fine:,}** {c} amendă!",
                    color=config.COLOR_ERROR,
                )
            )

    # ─── /richest ────────────────────────────────────────────────────────────

    @app_commands.command(name="richest", description="Top 10 cei mai bogați (RDN)")
    async def richest(self, interaction: discord.Interaction):
        lb = await db.get_economy_leaderboard(interaction.guild.id)
        if not lb:
            return await interaction.response.send_message(
                embed=error_embed("Nu există date încă."), ephemeral=True
            )
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        c = _rdn()
        for i, row in enumerate(lb):
            user = interaction.guild.get_member(row["user_id"])
            name = user.display_name if user else f"ID:{row['user_id']}"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — {row['total']:,} {c}")
        await interaction.response.send_message(
            embed=embed(
                title=f"💰 Top bogați — {_rdn()}",
                description="\n".join(lines),
                color=config.COLOR_ECONOMY,
            )
        )

    # ─── /shop ─────────────────────────────────────────────────────────────

    @app_commands.command(name="shop", description="Magazinul GDP — prețuri în RDN")
    async def shop(self, interaction: discord.Interaction):
        chunks = []
        for key, v in config.SHOP_ITEMS.items():
            tag = f" `[{v['tag']}]`" if v.get("tag") else ""
            perks = "\n".join(f"• {p}" for p in v.get("perks", [])[:6])
            chunks.append(
                f"**{v['name']}**{tag} — **{v['price']:,}** {_rdn()}\n"
                f"_{v['description']}_\n{perks}\n`cheie: {key}`\n"
            )
        desc = "\n".join(chunks)[:4000]
        e = embed(
            title="🛒 Shop GDP — RDN",
            description=desc + f"\n\nCumpără cu `/buy` sau schimbă cu `/trade swap`.",
            color=config.COLOR_ECONOMY,
        )
        await interaction.response.send_message(embed=e)

    # ─── /buy ────────────────────────────────────────────────────────────────

    @app_commands.command(name="buy", description="Cumpără un produs din shop cu RDN")
    @app_commands.describe(item="Cheia produsului (ex: vip_rank)")
    async def buy(self, interaction: discord.Interaction, item: str):
        item = item.lower().strip()
        if item not in config.SHOP_ITEMS:
            keys = ", ".join(f"`{k}`" for k in config.SHOP_ITEMS)
            return await interaction.response.send_message(
                embed=error_embed(f"Produs inexistent. Disponibile: {keys}"), ephemeral=True
            )
        shop_item = config.SHOP_ITEMS[item]
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        c = _rdn()
        if data["balance"] < shop_item["price"]:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Îți lipsesc **{shop_item['price'] - data['balance']:,}** {c}."
                ),
                ephemeral=True,
            )
        await db.update_balance(interaction.user.id, interaction.guild.id, -shop_item["price"])
        await db.add_to_inventory(interaction.user.id, interaction.guild.id, item)
        if item == "lootbox":
            reward = random.randint(8, 85)
            await db.update_balance(interaction.user.id, interaction.guild.id, reward)
            warn = await self._sync_shop_roles_from_inventory(
                interaction.user, interaction.guild
            )
            desc = f"Ai primit **{reward:,}** {c} din cutie!"
            if warn:
                desc += "\n" + "\n".join(warn)
            return await interaction.response.send_message(
                embed=embed(
                    title="📦 Loot Box",
                    description=desc,
                    color=config.COLOR_ECONOMY,
                )
            )
        warn = await self._sync_shop_roles_from_inventory(
            interaction.user, interaction.guild
        )
        msg = (
            f"Ai cumpărat **{shop_item['name']}** pentru **{shop_item['price']:,}** {c}!\n"
        )
        if item in self._shop_item_roles():
            msg += "🎭 Rolul legat de acest item a fost actualizat automat pe Discord."
        else:
            msg += "Contactează staff-ul dacă e nevoie de activare manuală (tag etc.)."
        if warn:
            msg += "\n" + "\n".join(warn)
        await interaction.response.send_message(embed=success_embed(msg))

    @buy.autocomplete("item")
    async def buy_item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._shop_keys_autocomplete(interaction, current)

    # ─── /inventory ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="inventory",
        description="Vezi itemele din inventar și rolurile legate (se sincronizează automat)",
    )
    async def inventory(self, interaction: discord.Interaction):
        await interaction.response.defer()
        warn = await self._sync_shop_roles_from_inventory(
            interaction.user, interaction.guild
        )
        items = await db.get_inventory(interaction.user.id, interaction.guild.id)
        if not items:
            e = embed(
                title="🎒 Inventar gol",
                description=f"Cumpără din `/shop` cu {_rdn()}.",
                color=config.COLOR_ECONOMY,
            )
            if warn:
                e.add_field(name="Notițe", value="\n".join(warn)[:1024], inline=False)
            return await interaction.followup.send(embed=e)

        lines = []
        role_map = self._shop_item_roles()
        for row in items:
            shop = config.SHOP_ITEMS.get(row["item_key"])
            name = shop["name"] if shop else row["item_key"]
            rid = role_map.get(row["item_key"])
            if rid:
                role = interaction.guild.get_role(rid)
                tag = f" → 🎭 {role.mention}" if role else f" → rol `ID:{rid}`"
            else:
                tag = ""
            lines.append(
                f"• **{name}** (`{row['item_key']}`) × **{row['quantity']}**{tag}"
            )
        desc = "\n".join(lines)
        if warn:
            desc += "\n\n" + "\n".join(warn)
        await interaction.followup.send(
            embed=embed(
                title=f"🎒 Inventar — {interaction.user.display_name}",
                description=desc[:4000],
                color=config.COLOR_ECONOMY,
                footer="Dacă dai trade sau nu mai ai un item, rolul asociat ți se scoate automat.",
            )
        )

    # ─── /coinflip ───────────────────────────────────────────────────────────

    @app_commands.command(name="coinflip", description="Pariază RDN pe cap sau pajură")
    @app_commands.describe(bet="Pariul", choice="cap sau pajura")
    async def coinflip(self, interaction: discord.Interaction, bet: int, choice: str):
        choice = choice.lower()
        if choice not in ("cap", "pajura"):
            return await interaction.response.send_message(
                embed=error_embed("Scrie `cap` sau `pajura`."), ephemeral=True
            )
        if bet <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Pariul trebuie să fie pozitiv."), ephemeral=True
            )
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        c = _rdn()
        if data["balance"] < bet:
            return await interaction.response.send_message(
                embed=error_embed(f"Balanță insuficientă! Ai **{data['balance']:,}** {c}."),
                ephemeral=True,
            )
        result = random.choice(["cap", "pajura"])
        won = result == choice
        change = bet if won else -bet
        await db.update_balance(interaction.user.id, interaction.guild.id, change)
        new_bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
        await interaction.response.send_message(
            embed=embed(
                title="🪙 " + ("Câștig!" if won else "Pierdere"),
                description=(
                    f"Rezultat: **{result}**\n"
                    f"{'+' if won else '-'}{bet:,} {c}\n"
                    f"Balanță: **{new_bal:,}** {c}"
                ),
                color=config.COLOR_SUCCESS if won else config.COLOR_ERROR,
            )
        )


async def setup(bot):
    await bot.add_cog(Economy(bot))
