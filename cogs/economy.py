import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import random

import config
from utils import database as db
from utils.helpers import success_embed, error_embed, embed


def _casino_draw_card() -> int:
    r = random.randint(1, 13)
    if r > 10:
        return 10
    if r == 1:
        return 11
    return r


def _casino_hand_value(cards: list[int]) -> int:
    total = sum(cards)
    aces = sum(1 for c in cards if c == 11)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def _fmt_cards(cards: list[int], hidden_second: bool = False) -> str:
    if hidden_second and len(cards) >= 2:
        return f"{cards[0]} + ?"
    return " · ".join(str(c) for c in cards)


class _BlackjackView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, bet: int, player: list, dealer: list):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.bet = bet
        self.player = list(player)
        self.dealer = list(dealer)
        self._done = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                embed=error_embed("Nu e rândul tău la acest blackjack."), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Carte", style=discord.ButtonStyle.primary, row=0)
    async def hit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._done:
            return await interaction.response.defer()
        self.player.append(_casino_draw_card())
        pv = _casino_hand_value(self.player)
        if pv > 21:
            self._done = True
            for c in self.children:
                c.disabled = True
            curname = _rdn()
            bal = (await db.get_economy(self.user_id, self.guild_id))["balance"]
            await interaction.response.edit_message(
                embed=embed(
                    title="💥 Bust",
                    description=(
                        f"Mâna ta: **{_fmt_cards(self.player)}** = **{pv}**\n"
                        f"Ai pierdut miza de **{self.bet:,}** {curname}.\n"
                        f"💵 Balanță: **{bal:,}** {curname}"
                    ),
                    color=config.COLOR_ERROR,
                ),
                view=self,
            )
            return
        await interaction.response.edit_message(
            embed=embed(
                title="🃏 Blackjack",
                description=(
                    f"**Tu:** {_fmt_cards(self.player)} → **{_casino_hand_value(self.player)}**\n"
                    f"**Dealer:** {_fmt_cards(self.dealer, hidden_second=True)} (vizibil **{self.dealer[0]}**)\n"
                    f"Miza: **{self.bet:,}** {_rdn()}"
                ),
                color=config.COLOR_ECONOMY,
            ),
            view=self,
        )

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.secondary, row=0)
    async def stand_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._done:
            return await interaction.response.defer()
        self._done = True
        for c in self.children:
            c.disabled = True
        dealer = list(self.dealer)
        while _casino_hand_value(dealer) < 17:
            dealer.append(_casino_draw_card())
        pv = _casino_hand_value(self.player)
        dv = _casino_hand_value(dealer)
        pay = 0
        if dv > 21 or pv > dv:
            pay = 2 * self.bet
            title, color = "✅ Câștig", config.COLOR_SUCCESS
            extra = f"Ai **{pv}**, dealer **{dv}**. Primești **{pay:,}** {_rdn()}."
        elif pv == dv:
            pay = self.bet
            title, color = "↔️ Remiză", config.COLOR_WARNING
            extra = f"**{pv}** egal. Ți se întoarce miza."
        else:
            title, color = "❌ Pierdere", config.COLOR_ERROR
            extra = f"Ai **{pv}**, dealer **{dv}**. Ai pierdut miza."
        if pay:
            await db.update_balance(self.user_id, self.guild_id, pay)
        bal = (await db.get_economy(self.user_id, self.guild_id))["balance"]
        await interaction.response.edit_message(
            embed=embed(
                title=title,
                description=(
                    f"**Tu:** {_fmt_cards(self.player)} → **{pv}**\n"
                    f"**Dealer:** {_fmt_cards(dealer)} → **{dv}**\n"
                    f"{extra}\n💵 Balanță: **{bal:,}** {_rdn()}"
                ),
                color=color,
            ),
            view=self,
        )


class _PvpDuelView(discord.ui.View):
    def __init__(self, bot: commands.Bot, challenge_id: int):
        super().__init__(timeout=float(config.PVP_BET_EXPIRE_MINUTES * 60))
        self.bot = bot
        self.challenge_id = challenge_id

    @discord.ui.button(label="Acceptă pariu", style=discord.ButtonStyle.success, row=0)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await db.get_pvp_challenge(self.challenge_id)
        if not row:
            for c in self.children:
                c.disabled = True
            await interaction.response.edit_message(content="Provocare invalidă.", embed=None, view=self)
            return
        exp = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > exp:
            await db.delete_pvp_challenge(self.challenge_id)
            for c in self.children:
                c.disabled = True
            await interaction.response.edit_message(content="⏱️ Provocarea a expirat.", embed=None, view=self)
            return
        if interaction.user.id != row["opponent_id"]:
            return await interaction.response.send_message(
                embed=error_embed("Doar persoana provocată poate accepta."), ephemeral=True
            )
        g = row["guild_id"]
        amt = row["amount"]
        cid, oid = row["challenger_id"], row["opponent_id"]
        checo = await db.get_economy(cid, g)
        opco = await db.get_economy(oid, g)
        c = _rdn()
        if checo["balance"] < amt or opco["balance"] < amt:
            await db.delete_pvp_challenge(self.challenge_id)
            for b in self.children:
                b.disabled = True
            return await interaction.response.edit_message(
                embed=error_embed("Unul dintre voi nu mai are destui bani — pariu anulat."),
                view=self,
            )
        await db.update_balance(cid, g, -amt)
        await db.update_balance(oid, g, -amt)
        flip = random.choice([cid, oid])
        await db.update_balance(flip, g, 2 * amt)
        await db.delete_pvp_challenge(self.challenge_id)
        for b in self.children:
            b.disabled = True
        winner = interaction.guild.get_member(flip)
        wname = winner.mention if winner else f"<@{flip}>"
        await interaction.response.edit_message(
            embed=embed(
                title="🎲 Pariu 1v1",
                description=(
                    f"{'🪙' * 3} **{wname}** câștigă **{2 * amt:,}** {c} "
                    f"(amândoi au mizat **{amt:,}** {c})."
                ),
                color=config.COLOR_SUCCESS if flip == interaction.user.id else config.COLOR_FUN,
            ),
            view=self,
        )

    @discord.ui.button(label="Refuză", style=discord.ButtonStyle.danger, row=0)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await db.get_pvp_challenge(self.challenge_id)
        if not row:
            return await interaction.response.send_message(
                embed=error_embed("Provocarea nu mai există."), ephemeral=True
            )
        uid = interaction.user.id
        if uid not in (row["challenger_id"], row["opponent_id"]):
            return await interaction.response.send_message(
                embed=error_embed("Nu ești parte din acest pariu."), ephemeral=True
            )
        await db.delete_pvp_challenge(self.challenge_id)
        for b in self.children:
            b.disabled = True
        await interaction.response.edit_message(
            content=f"❌ Pariu refuzat de {interaction.user.mention}.",
            embed=None,
            view=self,
        )

    async def on_timeout(self):
        row = await db.get_pvp_challenge(self.challenge_id)
        if row:
            await db.delete_pvp_challenge(self.challenge_id)
        if not row or not row.get("message_id"):
            return
        channel = self.bot.get_channel(row["channel_id"])
        if not channel:
            return
        try:
            msg = await channel.fetch_message(row["message_id"])
            await msg.edit(content="⏱️ Provocarea a expirat.", embed=None, view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass


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

    @app_commands.command(
        name="deposit",
        description="Mută RDN din cash în bancă — banii din bancă nu pot fi furăți la /rob",
    )
    @app_commands.describe(amount="Suma (cash → bancă)")
    async def deposit_cmd(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Folosește o sumă pozitivă."), ephemeral=True
            )
        ok = await db.bank_deposit(interaction.user.id, interaction.guild.id, amount)
        c = _rdn()
        if not ok:
            data = await db.get_economy(interaction.user.id, interaction.guild.id)
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Nu ai destui bani în cash. Ai **{data['balance']:,}** {c}."
                ),
                ephemeral=True,
            )
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(
            embed=success_embed(
                f"Ai depus **{amount:,}** {c} în bancă.\n"
                f"💵 Cash: **{data['balance']:,}** · 🏦 Bancă: **{data['bank']:,}** {c}"
            )
        )

    @app_commands.command(name="withdraw", description="Mută RDN din bancă în cash")
    @app_commands.describe(amount="Suma (bancă → cash)")
    async def withdraw_cmd(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            return await interaction.response.send_message(
                embed=error_embed("Folosește o sumă pozitivă."), ephemeral=True
            )
        ok = await db.bank_withdraw(interaction.user.id, interaction.guild.id, amount)
        c = _rdn()
        if not ok:
            data = await db.get_economy(interaction.user.id, interaction.guild.id)
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Nu ai destul în bancă. Ai **{data['bank']:,}** {c}."
                ),
                ephemeral=True,
            )
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(
            embed=success_embed(
                f"Ai retras **{amount:,}** {c}.\n"
                f"💵 Cash: **{data['balance']:,}** · 🏦 Bancă: **{data['bank']:,}** {c}"
            )
        )

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
        description=f"Jocuri cu miză din cash ({config.MINIGAME_BET_MIN}-{config.MINIGAME_BET_MAX} {_rdn()}), max {config.MINIGAMES_PER_DAY}/zi",
    )

    async def _begin_minigame_round(self, interaction: discord.Interaction, bet: int) -> bool:
        """Înregistrează runda și reține miza. Trimite erori și returnează False dacă nu se poate."""
        if bet < config.MINIGAME_BET_MIN or bet > config.MINIGAME_BET_MAX:
            await interaction.response.send_message(
                embed=error_embed(
                    f"Miza trebuie între **{config.MINIGAME_BET_MIN:,}** și "
                    f"**{config.MINIGAME_BET_MAX:,}** {_rdn()}."
                ),
                ephemeral=True,
            )
            return False
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < bet:
            await interaction.response.send_message(
                embed=error_embed(
                    f"Îți trebuie **{bet:,}** {_rdn()} în cash. Ai **{data['balance']:,}**."
                ),
                ephemeral=True,
            )
            return False
        allowed = await db.try_register_minigame_play(
            interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
        )
        if not allowed:
            rem = await db.get_minigames_remaining(
                interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
            )
            await interaction.response.send_message(
                embed=error_embed(
                    f"Limită zilnică (**{config.MINIGAMES_PER_DAY}** jocuri). Rămase: **{rem}**."
                ),
                ephemeral=True,
            )
            return False
        await db.update_balance(interaction.user.id, interaction.guild.id, -bet)
        return True

    @minigame.command(name="dice", description="Zar 2d6 — sumă mare dublează miza; mic pierzi tot")
    @app_commands.describe(bet="Miza din cash")
    async def mg_dice(self, interaction: discord.Interaction, bet: int):
        if not await self._begin_minigame_round(interaction, bet):
            return
        a, b = random.randint(1, 6), random.randint(1, 6)
        s = a + b
        c = _rdn()
        if s >= 10:
            payout = bet * 2
            note = f"🎲 **{a}+{b}={s}** — mare! Primești **{payout:,}** {c} (x2 miză)."
        elif s >= 7:
            payout = bet
            note = f"🎲 **{a}+{b}={s}** — remiză: îți întorci miza (**{payout:,}** {c})."
        else:
            payout = 0
            note = f"🎲 **{a}+{b}={s}** — sumă mică. Ai pierdut miza (**{bet:,}** {c})."
        if payout:
            await db.update_balance(interaction.user.id, interaction.guild.id, payout)
        bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
        left = await db.get_minigames_remaining(
            interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
        )
        await interaction.response.send_message(
            embed=embed(
                title="🎲 Dice",
                description=f"{note}\n💵 Balanță: **{bal:,}** {c}\n🎮 Minigame rămase azi: **{left}**",
                color=config.COLOR_ECONOMY if payout >= bet else config.COLOR_ERROR,
            )
        )

    @minigame.command(name="guess", description="Ghicește 1–10 — exact triplează miza; altfel pierzi")
    @app_commands.describe(numar="Numărul tău (1-10)", bet="Miza din cash")
    async def mg_guess(self, interaction: discord.Interaction, numar: int, bet: int):
        if not 1 <= numar <= 10:
            return await interaction.response.send_message(
                embed=error_embed("Alege un număr între **1** și **10**."), ephemeral=True
            )
        if not await self._begin_minigame_round(interaction, bet):
            return
        secret = random.randint(1, 10)
        hit = numar == secret
        if hit:
            payout = bet * 3
            line = f"🎯 Numărul era **{secret}**! Primești **{payout:,}** {_rdn()} (x3 miză)."
            col = config.COLOR_SUCCESS
        else:
            payout = 0
            line = f"❌ Numărul era **{secret}**, tu **{numar}**. Ai pierdut **{bet:,}** {_rdn()}."
            col = config.COLOR_ERROR
        if payout:
            await db.update_balance(interaction.user.id, interaction.guild.id, payout)
        bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
        left = await db.get_minigames_remaining(
            interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
        )
        await interaction.response.send_message(
            embed=embed(
                title="🔢 Guess",
                description=(
                    f"{line}\n💵 Balanță: **{bal:,}** {_rdn()}\n🎮 Mai ai **{left}** minigame-uri azi."
                ),
                color=col,
            )
        )

    @minigame.command(name="slots", description="3 role — triplu x4 miză, două egale x2, altfel pierzi")
    @app_commands.describe(bet="Miza din cash")
    async def mg_slots(self, interaction: discord.Interaction, bet: int):
        if not await self._begin_minigame_round(interaction, bet):
            return
        syms = ["🍒", "🍋", "⭐", "💎", "7️⃣"]
        r = [random.choice(syms) for _ in range(3)]
        c = _rdn()
        if r[0] == r[1] == r[2]:
            payout = bet * 4
            line = f"{' | '.join(r)}\n💎 TRIPLU! **{payout:,}** {c}."
            col = config.COLOR_SUCCESS
        elif r[0] == r[1] or r[1] == r[2] or r[0] == r[2]:
            payout = bet * 2
            line = f"{' | '.join(r)}\n✨ Două la fel — **{payout:,}** {c}."
            col = config.COLOR_ECONOMY
        else:
            payout = 0
            line = f"{' | '.join(r)}\nNicio combinație — ai pierdut **{bet:,}** {c}."
            col = config.COLOR_ERROR
        if payout:
            await db.update_balance(interaction.user.id, interaction.guild.id, payout)
        bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
        left = await db.get_minigames_remaining(
            interaction.user.id, interaction.guild.id, config.MINIGAMES_PER_DAY
        )
        await interaction.response.send_message(
            embed=embed(
                title="🎰 Slots",
                description=f"{line}\n💵 Balanță: **{bal:,}** {c}\n🎮 Mai ai **{left}** minigame-uri azi.",
                color=col,
            )
        )

    # ─── Grup /casino ────────────────────────────────────────────────────────

    casino = app_commands.Group(
        name="casino",
        description="Blackjack și Risk it all — nu folosesc limita /minigame (high stakes)",
    )

    @casino.command(
        name="blackjack",
        description="Blackjack cu butoane Carte/Stop (dealer trage până la 17)",
    )
    @app_commands.describe(bet="Miza din cash")
    async def casino_blackjack(self, interaction: discord.Interaction, bet: int):
        mx = getattr(config, "CASINO_BLACKJACK_MAX_BET", 5000)
        if bet < config.MINIGAME_BET_MIN or bet > mx:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Miza blackjack: **{config.MINIGAME_BET_MIN:,}** – **{mx:,}** {_rdn()}."
                ),
                ephemeral=True,
            )
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if data["balance"] < bet:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Îți lipsește miza în cash. Ai **{data['balance']:,}** {_rdn()}."
                ),
                ephemeral=True,
            )
        await interaction.response.defer()
        await db.update_balance(interaction.user.id, interaction.guild.id, -bet)
        player = [_casino_draw_card(), _casino_draw_card()]
        dealer = [_casino_draw_card(), _casino_draw_card()]
        pv = _casino_hand_value(player)
        dv = _casino_hand_value(dealer)
        c = _rdn()
        if pv == 21:
            if dv == 21:
                await db.update_balance(interaction.user.id, interaction.guild.id, bet)
                bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
                return await interaction.followup.send(
                    embed=embed(
                        title="🃏 Blackjack",
                        description=(
                            f"Amândoi **21** — remiză. Ți se întoarce miza.\n"
                            f"💵 Balanță: **{bal:,}** {c}"
                        ),
                        color=config.COLOR_WARNING,
                    )
                )
            pay = int(bet * 2.5)
            await db.update_balance(interaction.user.id, interaction.guild.id, pay)
            bal = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
            return await interaction.followup.send(
                embed=embed(
                    title="🃏 Blackjack natural!",
                    description=(
                        f"Tu **21**, dealer **{dv}**. Primești **{pay:,}** {c}.\n"
                        f"💵 Balanță: **{bal:,}** {c}"
                    ),
                    color=config.COLOR_SUCCESS,
                )
            )
        view = _BlackjackView(
            interaction.user.id, interaction.guild.id, bet, player, dealer
        )
        await interaction.followup.send(
            embed=embed(
                title="🃏 Blackjack",
                description=(
                    f"**Tu:** {_fmt_cards(player)} → **{pv}**\n"
                    f"**Dealer:** {_fmt_cards(dealer, hidden_second=True)} (vizibil **{dealer[0]}**)\n"
                    f"Miza: **{bet:,}** {c}\n\nApasă **Carte** sau **Stop**."
                ),
                color=config.COLOR_ECONOMY,
            ),
            view=view,
        )

    @casino.command(
        name="riskitall",
        description="Doar cash: 1% șansă x10; dacă pierzi, pierzi tot cash-ul (banca e sigură)",
    )
    async def casino_riskitall(self, interaction: discord.Interaction):
        data = await db.get_economy(interaction.user.id, interaction.guild.id)
        bal = data["balance"]
        if bal <= 0:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"N-ai cash de riscat. Folosește `/withdraw` sau câștigă {_rdn()}."
                ),
                ephemeral=True,
            )
        now = datetime.now(timezone.utc)
        hr = getattr(config, "RISKITALL_COOLDOWN_HOURS", 24)
        if data.get("last_riskitall"):
            last = datetime.fromisoformat(data["last_riskitall"])
            if now - last < timedelta(hours=hr):
                rem = timedelta(hours=hr) - (now - last)
                h, m = divmod(int(rem.total_seconds()), 3600)
                mm = m // 60
                return await interaction.response.send_message(
                    embed=error_embed(f"Cooldown Risk it all: revino în **{h}h {mm}m**."),
                    ephemeral=True,
                )
        c = _rdn()
        await db.set_last_riskitall(interaction.user.id, interaction.guild.id, now.isoformat())
        win = random.random() < 0.01
        if win:
            add = bal * 10 - bal
            await db.update_balance(interaction.user.id, interaction.guild.id, add)
            nb = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
            await interaction.response.send_message(
                embed=embed(
                    title="🌟 RISK IT ALL — CÂȘTIG",
                    description=(
                        f"1% s-a întâmplat! Cash-ul tău (**{bal:,}** {c}) a fost **înmulțit cu 10**.\n"
                        f"💵 Cash acum: **{nb:,}** {c}\n"
                        f"🏦 Banca nu a fost atinsă (**{data['bank']:,}** {c})."
                    ),
                    color=config.COLOR_SUCCESS,
                )
            )
        else:
            await db.update_balance(interaction.user.id, interaction.guild.id, -bal)
            nb = (await db.get_economy(interaction.user.id, interaction.guild.id))["balance"]
            await interaction.response.send_message(
                embed=embed(
                    title="💀 Risk it all — pierdere",
                    description=(
                        f"Ai pierdut **tot cash-ul** (**{bal:,}** {c}). Banca ta rămâne **{data['bank']:,}** {c}.\n"
                        f"💵 Cash acum: **{nb:,}** {c}"
                    ),
                    color=config.COLOR_ERROR,
                )
            )

    # ─── Grup /bet (pariu 1v1) ───────────────────────────────────────────────

    bet_group = app_commands.Group(name="bet", description="Pariu cu alt membru (amândoi mizează egal)")

    @bet_group.command(name="duel", description="Provocă pe cineva: amândoi pariați, câștigătorul unul primește totul")
    @app_commands.describe(opponent="Membrul provocat", amount="Miza fiecăruia (din cash)")
    async def bet_duel(
        self, interaction: discord.Interaction, opponent: discord.Member, amount: int
    ):
        if opponent.bot or opponent.id == interaction.user.id:
            return await interaction.response.send_message(
                embed=error_embed("Alege un membru real, nu pe tine însuți."), ephemeral=True
            )
        if amount < config.MINIGAME_BET_MIN:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Miza minimă: **{config.MINIGAME_BET_MIN:,}** {_rdn()}."
                ),
                ephemeral=True,
            )
        ch = await db.get_economy(interaction.user.id, interaction.guild.id)
        op = await db.get_economy(opponent.id, interaction.guild.id)
        c = _rdn()
        if ch["balance"] < amount:
            return await interaction.response.send_message(
                embed=error_embed(f"Nu ai **{amount:,}** {c} în cash."), ephemeral=True
            )
        if op["balance"] < amount:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"{opponent.mention} n-are **{amount:,}** {c} în cash."
                ),
                ephemeral=True,
            )
        now = datetime.now(timezone.utc)
        exp = (now + timedelta(minutes=config.PVP_BET_EXPIRE_MINUTES)).isoformat()
        await db.delete_open_pvp_challenges_between(
            interaction.guild.id, interaction.user.id, opponent.id
        )
        cid = await db.create_pvp_challenge(
            interaction.guild.id,
            interaction.channel.id,
            0,
            interaction.user.id,
            opponent.id,
            amount,
            now.isoformat(),
            exp,
        )
        view = _PvpDuelView(self.bot, cid)
        e = embed(
            title="⚔️ Provocare pariu",
            description=(
                f"{interaction.user.mention} pariază **{amount:,}** {c} cu {opponent.mention}.\n"
                f"Amândoi plătesc miza; **un câștigător** ia **{2 * amount:,}** {c}.\n"
                f"⏱️ Acceptă în **{config.PVP_BET_EXPIRE_MINUTES}** minute."
            ),
            color=config.COLOR_FUN,
        )
        await interaction.response.send_message(embed=e, view=view)
        msg = await interaction.original_response()
        await db.update_pvp_challenge_message_id(cid, msg.id)

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

    @app_commands.command(
        name="rob",
        description="Fură doar din CASH (nu din bancă). Ai cooldown între încercări.",
    )
    @app_commands.describe(member="Ținta")
    async def rob(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("Nu te poți jefui singur."), ephemeral=True
            )
        now = datetime.now(timezone.utc)
        robber_data = await db.get_economy(interaction.user.id, interaction.guild.id)
        if robber_data.get("last_rob"):
            last = datetime.fromisoformat(robber_data["last_rob"])
            cd = timedelta(minutes=getattr(config, "ROB_COOLDOWN_MINUTES", 45))
            if now - last < cd:
                rem = cd - (now - last)
                m = max(1, int(rem.total_seconds() // 60))
                return await interaction.response.send_message(
                    embed=error_embed(f"Cooldown /rob: revino în **{m}** minute."),
                    ephemeral=True,
                )
        victim_data = await db.get_economy(member.id, interaction.guild.id)
        if victim_data["balance"] < 50:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"{member.mention} are prea puțin cash (min. 50). Banii din **bancă** nu se fură."
                ),
                ephemeral=True,
            )
        success = random.random() < 0.40
        c = _rdn()
        await db.set_last_rob(interaction.user.id, interaction.guild.id, now.isoformat())
        if success:
            cap = min(victim_data["balance"] // 2, 500)
            stolen = random.randint(1, max(1, cap))
            stolen = min(stolen, victim_data["balance"])
            await db.transfer_coins(member.id, interaction.guild.id, interaction.user.id, stolen)
            await interaction.response.send_message(
                embed=embed(
                    title="🦹 Jaf reușit!",
                    description=(
                        f"Ai luat **{stolen:,}** {c} cash de la {member.mention}!\n"
                        f"_(Banii din bancă ai lui sunt în siguranță.)_"
                    ),
                    color=config.COLOR_SUCCESS,
                )
            )
        else:
            fine = random.randint(50, 200)
            fine = min(fine, robber_data["balance"])
            if fine > 0:
                await db.transfer_coins(
                    interaction.user.id, interaction.guild.id, member.id, fine
                )
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
