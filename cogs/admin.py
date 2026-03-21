<<<<<<< HEAD
import discord
from discord.ext import commands
from discord import app_commands
import sys
import os

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed, warning_embed


class AnnounceModal(discord.ui.Modal, title="📢 Trimite anunț"):
    """Formular pentru titlu + mesaj (ca meniul Discord)."""

    def __init__(self, channel: discord.TextChannel, ping_everyone: bool):
        super().__init__(timeout=300)
        self.target_channel = channel
        self.ping_everyone = ping_everyone
        self.title_in = discord.ui.TextInput(
            label="Titlu anunț",
            placeholder="Ex: Actualizare regulament",
            max_length=256,
            required=True,
        )
        self.body = discord.ui.TextInput(
            label="Mesaj",
            style=discord.TextStyle.paragraph,
            placeholder="Textul anunțului...",
            max_length=2000,
            required=True,
        )
        self.add_item(self.title_in)
        self.add_item(self.body)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        e = embed(
            title=f"📢 {self.title_in.value}",
            description=self.body.value,
            color=config.COLOR_PRIMARY,
            thumbnail=interaction.guild.icon.url if interaction.guild.icon else None,
        )
        e.set_footer(text=f"Anunț de la {interaction.user.display_name}")
        content = "@everyone" if self.ping_everyone else None
        try:
            await self.target_channel.send(content=content, embed=e)
        except Exception as ex:
            return await interaction.followup.send(
                embed=error_embed(f"Nu am putut trimite anunțul: {ex}"), ephemeral=True
            )
        await interaction.followup.send(
            embed=success_embed(f"Anunț trimis în {self.target_channel.mention}!"), ephemeral=True
        )


class CustomEmbedModal(discord.ui.Modal, title="📦 Embed personalizat"):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=300)
        self.target_channel = channel
        self.title_in = discord.ui.TextInput(
            label="Titlu",
            placeholder="Titlul embed-ului",
            max_length=256,
            required=True,
        )
        self.description = discord.ui.TextInput(
            label="Descriere",
            style=discord.TextStyle.paragraph,
            placeholder="Conținutul principal...",
            max_length=4000,
            required=True,
        )
        self.color_hex = discord.ui.TextInput(
            label="Culoare (hex, opțional)",
            placeholder="#5865F2 sau lasă gol",
            max_length=7,
            required=False,
        )
        self.add_item(self.title_in)
        self.add_item(self.description)
        self.add_item(self.color_hex)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw = (self.color_hex.value or "").strip()
        color_int = config.COLOR_PRIMARY
        if raw:
            try:
                color_int = int(raw.lstrip("#"), 16)
            except ValueError:
                color_int = config.COLOR_PRIMARY
        e = embed(title=self.title_in.value, description=self.description.value, color=color_int)
        try:
            await self.target_channel.send(embed=e)
        except Exception as ex:
            return await interaction.followup.send(
                embed=error_embed(f"Nu am putut trimite embed-ul: {ex}"), ephemeral=True
            )
        await interaction.followup.send(
            embed=success_embed(f"Embed trimis în {self.target_channel.mention}!"), ephemeral=True
        )


class Admin(commands.Cog, name="Admin"):
    """Comenzi de administrare a botului."""

    def __init__(self, bot):
        self.bot = bot

    # ─── /setlog ─────────────────────────────────────────────────────────────

    @app_commands.command(name="setlog", description="[Admin] Setează canalul de log-uri")
    @app_commands.describe(channel="Canalul de log")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "log_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal de log setat la {channel.mention}.")
        )

    @app_commands.command(name="setlevel", description="[Admin] Setează canalul pentru level-up")
    @app_commands.describe(channel="Canalul de level-up")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlevel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "level_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal de level-up setat la {channel.mention}.")
        )

    @app_commands.command(name="setmemrole", description="[Admin] Setează rolul auto-assignat la join")
    @app_commands.describe(role="Rolul de membru")
    @app_commands.checks.has_permissions(administrator=True)
    async def setmemrole(self, interaction: discord.Interaction, role: discord.Role):
        await db.update_guild_setting(interaction.guild.id, "member_role", role.id)
        await interaction.response.send_message(
            embed=success_embed(f"Rol de membru setat: {role.mention}.")
        )

    @app_commands.command(name="setticketcat", description="[Admin] Setează categoria pentru tickete")
    @app_commands.describe(category="Categoria de canale")
    @app_commands.checks.has_permissions(administrator=True)
    async def setticketcat(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await db.update_guild_setting(interaction.guild.id, "ticket_category_id", category.id)
        await interaction.response.send_message(
            embed=success_embed(f"Categorie tickete setată: **{category.name}**.")
        )

    # ─── /announce ───────────────────────────────────────────────────────────

    @app_commands.command(name="announce", description="[Admin] Trimite un anunț (formular pe ecran)")
    @app_commands.describe(
        channel="Canalul de anunț",
        ping_everyone="Dacă să dea ping @everyone",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def announce(self, interaction: discord.Interaction,
                       channel: discord.TextChannel, ping_everyone: bool = False):
        await interaction.response.send_modal(AnnounceModal(channel, ping_everyone))

    # ─── /embed ──────────────────────────────────────────────────────────────

    @app_commands.command(name="embed", description="[Admin] Trimite un embed personalizat (formular pe ecran)")
    @app_commands.describe(channel="Canalul destinatar")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def send_embed(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.send_modal(CustomEmbedModal(channel))

    # ─── /addrole / /removerole ───────────────────────────────────────────────

    @app_commands.command(name="addrole", description="[Admin] Adaugă un rol unui utilizator")
    @app_commands.describe(member="Utilizatorul", role="Rolul")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send(
                embed=error_embed("Nu poți adăuga un rol mai mare sau egal cu al tău."), ephemeral=True
            )
        await member.add_roles(role)
        await interaction.followup.send(
            embed=success_embed(f"Rolul {role.mention} a fost adăugat lui {member.mention}."),
            ephemeral=True
        )

    @app_commands.command(name="removerole", description="[Admin] Elimină un rol de la un utilizator")
    @app_commands.describe(member="Utilizatorul", role="Rolul")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        await member.remove_roles(role)
        await interaction.followup.send(
            embed=success_embed(f"Rolul {role.mention} a fost eliminat de la {member.mention}."),
            ephemeral=True
        )

    # ─── /reload ─────────────────────────────────────────────────────────────

    @app_commands.command(name="reload", description="[Owner] Reîncarcă un cog")
    @app_commands.describe(cog="Numele cog-ului (ex: economy)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(
                embed=success_embed(f"Cog `{cog}` reîncărcat cu succes!")
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"Eroare la reîncărcare:\n```{e}```")
            )

    # ─── /synccommands ───────────────────────────────────────────────────────

    @app_commands.command(name="synccommands", description="[Admin] Sincronizează comenzile slash pe acest server")
    @app_commands.checks.has_permissions(administrator=True)
    async def synccommands(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            # Sincronizare pe serverul curent (instant) — astfel noul bot preia comenzile
            guild = discord.Object(id=interaction.guild.id)
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
            await interaction.followup.send(
                embed=success_embed(
                    f"Sincronizate **{len(synced)}** comenzi pe acest server!\n"
                    "Comenzile ar trebui să funcționeze acum."
                ),
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                embed=error_embed(f"Eroare la sincronizare:\n```{e}```"),
                ephemeral=True
            )

    # ─── /givecoins ──────────────────────────────────────────────────────────

    @app_commands.command(name="givecoins", description="[Admin] Oferă coins unui utilizator")
    @app_commands.describe(member="Utilizatorul", amount="Suma")
    @app_commands.checks.has_permissions(administrator=True)
    async def givecoins(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount == 0:
            return await interaction.response.send_message(
                embed=error_embed("Suma nu poate fi 0."), ephemeral=True
            )
        await db.update_balance(member.id, interaction.guild.id, amount)
        action = "adăugate" if amount > 0 else "eliminate"
        await interaction.response.send_message(
            embed=success_embed(f"**{abs(amount):,}** coins {action} {'lui' if amount > 0 else 'de la'} {member.mention}.")
        )

    # ─── /serversetup ────────────────────────────────────────────────────────

    @app_commands.command(name="serversetup", description="[Admin] Afișează configurația curentă a serverului")
    @app_commands.checks.has_permissions(administrator=True)
    async def serversetup(self, interaction: discord.Interaction):
        settings = await db.get_guild_settings(interaction.guild.id)

        def ch_str(ch_id):
            if not ch_id:
                return "❌ Nesetat"
            ch = interaction.guild.get_channel(ch_id)
            return ch.mention if ch else f"❌ ID invalid ({ch_id})"

        def role_str(role_id):
            if not role_id:
                return "❌ Nesetat"
            role = interaction.guild.get_role(role_id)
            return role.mention if role else f"❌ ID invalid ({role_id})"

        e = embed(
            title="⚙️ Configurație Server",
            color=config.COLOR_PRIMARY,
            fields=[
                ("👋 Canal Welcome", ch_str(settings.get("welcome_channel")), True),
                ("👋 Canal Goodbye", ch_str(settings.get("goodbye_channel")), True),
                ("📋 Canal Log", ch_str(settings.get("log_channel")), True),
                ("⭐ Canal Level-up", ch_str(settings.get("level_channel")), True),
                ("🎭 Rol Membru", role_str(settings.get("member_role")), True),
            ]
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
=======
import discord
from discord.ext import commands
from discord import app_commands
import sys
import os

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed, warning_embed


class Admin(commands.Cog, name="Admin"):
    """Comenzi de administrare a botului."""

    def __init__(self, bot):
        self.bot = bot

    # ─── /setlog ─────────────────────────────────────────────────────────────

    @app_commands.command(name="setlog", description="[Admin] Setează canalul de log-uri")
    @app_commands.describe(channel="Canalul de log")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "log_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal de log setat la {channel.mention}.")
        )

    @app_commands.command(name="setlevel", description="[Admin] Setează canalul pentru level-up")
    @app_commands.describe(channel="Canalul de level-up")
    @app_commands.checks.has_permissions(administrator=True)
    async def setlevel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "level_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal de level-up setat la {channel.mention}.")
        )

    @app_commands.command(name="setmemrole", description="[Admin] Setează rolul auto-assignat la join")
    @app_commands.describe(role="Rolul de membru")
    @app_commands.checks.has_permissions(administrator=True)
    async def setmemrole(self, interaction: discord.Interaction, role: discord.Role):
        await db.update_guild_setting(interaction.guild.id, "member_role", role.id)
        await interaction.response.send_message(
            embed=success_embed(f"Rol de membru setat: {role.mention}.")
        )

    @app_commands.command(name="setticketcat", description="[Admin] Setează categoria pentru tickete")
    @app_commands.describe(category="Categoria de canale")
    @app_commands.checks.has_permissions(administrator=True)
    async def setticketcat(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await db.update_guild_setting(interaction.guild.id, "ticket_category_id", category.id)
        await interaction.response.send_message(
            embed=success_embed(f"Categorie tickete setată: **{category.name}**.")
        )

    # ─── /announce ───────────────────────────────────────────────────────────

    @app_commands.command(name="announce", description="[Admin] Trimite un anunț formatat")
    @app_commands.describe(
        channel="Canalul de anunț",
        title="Titlul",
        message="Mesajul",
        ping_everyone="Dacă să dea ping @everyone"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def announce(self, interaction: discord.Interaction,
                        channel: discord.TextChannel, title: str,
                        message: str, ping_everyone: bool = False):
        e = embed(
            title=f"📢 {title}",
            description=message,
            color=config.COLOR_PRIMARY,
            thumbnail=interaction.guild.icon.url if interaction.guild.icon else None
        )
        e.set_footer(text=f"Anunț de la {interaction.user.display_name}")
        content = "@everyone" if ping_everyone else None
        await channel.send(content=content, embed=e)
        await interaction.response.send_message(
            embed=success_embed(f"Anunț trimis în {channel.mention}!"), ephemeral=True
        )

    # ─── /embed ──────────────────────────────────────────────────────────────

    @app_commands.command(name="embed", description="[Admin] Trimite un embed personalizat")
    @app_commands.describe(
        channel="Canalul",
        title="Titlul embed-ului",
        description="Conținutul",
        color="Culoare hex (ex: #5865F2, opțional)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def send_embed(self, interaction: discord.Interaction,
                          channel: discord.TextChannel, title: str,
                          description: str, color: str = "#5865F2"):
        try:
            color_int = int(color.lstrip("#"), 16)
        except ValueError:
            color_int = config.COLOR_PRIMARY
        e = embed(title=title, description=description, color=color_int)
        await channel.send(embed=e)
        await interaction.response.send_message(
            embed=success_embed(f"Embed trimis în {channel.mention}!"), ephemeral=True
        )

    # ─── /addrole / /removerole ───────────────────────────────────────────────

    @app_commands.command(name="addrole", description="[Admin] Adaugă un rol unui utilizator")
    @app_commands.describe(member="Utilizatorul", role="Rolul")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if role >= interaction.user.top_role and not interaction.user.guild_permissions.administrator:
            return await interaction.followup.send(
                embed=error_embed("Nu poți adăuga un rol mai mare sau egal cu al tău."), ephemeral=True
            )
        await member.add_roles(role)
        await interaction.followup.send(
            embed=success_embed(f"Rolul {role.mention} a fost adăugat lui {member.mention}."),
            ephemeral=True
        )

    @app_commands.command(name="removerole", description="[Admin] Elimină un rol de la un utilizator")
    @app_commands.describe(member="Utilizatorul", role="Rolul")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        await member.remove_roles(role)
        await interaction.followup.send(
            embed=success_embed(f"Rolul {role.mention} a fost eliminat de la {member.mention}."),
            ephemeral=True
        )

    # ─── /reload ─────────────────────────────────────────────────────────────

    @app_commands.command(name="reload", description="[Owner] Reîncarcă un cog")
    @app_commands.describe(cog="Numele cog-ului (ex: economy)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reload(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(
                embed=success_embed(f"Cog `{cog}` reîncărcat cu succes!")
            )
        except Exception as e:
            await interaction.response.send_message(
                embed=error_embed(f"Eroare la reîncărcare:\n```{e}```")
            )

    # ─── /synccommands ───────────────────────────────────────────────────────

    @app_commands.command(name="synccommands", description="[Admin] Sincronizează comenzile slash pe acest server")
    @app_commands.checks.has_permissions(administrator=True)
    async def synccommands(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            # Sincronizare pe serverul curent (instant) — astfel noul bot preia comenzile
            guild = discord.Object(id=interaction.guild.id)
            self.bot.tree.copy_global_to(guild=guild)
            synced = await self.bot.tree.sync(guild=guild)
            await interaction.followup.send(
                embed=success_embed(
                    f"Sincronizate **{len(synced)}** comenzi pe acest server!\n"
                    "Comenzile ar trebui să funcționeze acum."
                ),
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                embed=error_embed(f"Eroare la sincronizare:\n```{e}```"),
                ephemeral=True
            )

    # ─── /givecoins ──────────────────────────────────────────────────────────

    @app_commands.command(name="givecoins", description="[Admin] Oferă coins unui utilizator")
    @app_commands.describe(member="Utilizatorul", amount="Suma")
    @app_commands.checks.has_permissions(administrator=True)
    async def givecoins(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount == 0:
            return await interaction.response.send_message(
                embed=error_embed("Suma nu poate fi 0."), ephemeral=True
            )
        await db.update_balance(member.id, interaction.guild.id, amount)
        action = "adăugate" if amount > 0 else "eliminate"
        await interaction.response.send_message(
            embed=success_embed(f"**{abs(amount):,}** coins {action} {'lui' if amount > 0 else 'de la'} {member.mention}.")
        )

    # ─── /serversetup ────────────────────────────────────────────────────────

    @app_commands.command(name="serversetup", description="[Admin] Afișează configurația curentă a serverului")
    @app_commands.checks.has_permissions(administrator=True)
    async def serversetup(self, interaction: discord.Interaction):
        settings = await db.get_guild_settings(interaction.guild.id)

        def ch_str(ch_id):
            if not ch_id:
                return "❌ Nesetat"
            ch = interaction.guild.get_channel(ch_id)
            return ch.mention if ch else f"❌ ID invalid ({ch_id})"

        def role_str(role_id):
            if not role_id:
                return "❌ Nesetat"
            role = interaction.guild.get_role(role_id)
            return role.mention if role else f"❌ ID invalid ({role_id})"

        e = embed(
            title="⚙️ Configurație Server",
            color=config.COLOR_PRIMARY,
            fields=[
                ("👋 Canal Welcome", ch_str(settings.get("welcome_channel")), True),
                ("👋 Canal Goodbye", ch_str(settings.get("goodbye_channel")), True),
                ("📋 Canal Log", ch_str(settings.get("log_channel")), True),
                ("⭐ Canal Level-up", ch_str(settings.get("level_channel")), True),
                ("🎭 Rol Membru", role_str(settings.get("member_role")), True),
            ]
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
