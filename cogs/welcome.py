import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed


class WelcomeMessageModal(discord.ui.Modal):
    def __init__(self, title: str, setting_key: str, description_hint: str):
        super().__init__(title=title, timeout=300)
        self.setting_key = setting_key
        self.message = discord.ui.TextInput(
            label="Mesaj",
            style=discord.TextStyle.paragraph,
            placeholder=description_hint,
            required=True,
            max_length=1000,
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        await db.update_guild_setting(interaction.guild.id, self.setting_key, str(self.message))
        await interaction.response.send_message(
            embed=success_embed(f"Mesajul a fost setat la:\n> {self.message.value}"),
            ephemeral=True,
        )


class Welcome(commands.Cog, name="Welcome"):
    """Mesaje de bun venit și la revedere."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        settings = await db.get_guild_settings(guild.id)

        # Assign member role
        member_role_id = settings.get("member_role") or config.MEMBER_ROLE_ID
        if member_role_id:
            role = guild.get_role(member_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Auto-role la join")
                except Exception:
                    pass

        # Send welcome message
        ch_id = settings.get("welcome_channel") or config.WELCOME_CHANNEL_ID
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch:
            return

        custom_msg = settings.get("welcome_message")
        if custom_msg:
            msg = custom_msg.replace("{user}", member.mention).replace("{server}", guild.name).replace("{count}", str(guild.member_count))
        else:
            msg = f"Bine ai venit pe **{guild.name}**, {member.mention}! 🎉\nEști al **{guild.member_count}**-lea membru!"

        e = embed(
            title="👋 Membru nou!",
            description=msg,
            color=config.COLOR_SUCCESS,
            thumbnail=member.display_avatar.url,
            fields=[
                ("Cont creat", f"<t:{int(member.created_at.timestamp())}:R>", True),
                ("Membrii totali", str(guild.member_count), True),
            ]
        )
        await ch.send(embed=e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        settings = await db.get_guild_settings(guild.id)

        ch_id = settings.get("goodbye_channel") or config.GOODBYE_CHANNEL_ID
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch:
            return

        custom_msg = settings.get("goodbye_message")
        if custom_msg:
            msg = custom_msg.replace("{user}", str(member)).replace("{server}", guild.name)
        else:
            msg = f"**{member}** a părăsit serverul. Ne pare rău să te vedem plecând! 😢"

        e = embed(
            title="👋 La revedere!",
            description=msg,
            color=config.COLOR_ERROR,
            thumbnail=member.display_avatar.url,
            fields=[
                ("Membrii rămași", str(guild.member_count), True),
            ]
        )
        await ch.send(embed=e)

    # ─── /setwelcome ─────────────────────────────────────────────────────────

    @app_commands.command(name="setwelcome", description="[Admin] Setează canalul de bun venit")
    @app_commands.describe(channel="Canalul de welcome")
    @app_commands.checks.has_permissions(administrator=True)
    async def setwelcome(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "welcome_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal de welcome setat la {channel.mention}.")
        )

    @app_commands.command(name="setgoodbye", description="[Admin] Setează canalul de goodbye")
    @app_commands.describe(channel="Canalul de goodbye")
    @app_commands.checks.has_permissions(administrator=True)
    async def setgoodbye(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await db.update_guild_setting(interaction.guild.id, "goodbye_channel", channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Canal de goodbye setat la {channel.mention}.")
        )

    @app_commands.command(name="setwelcomemsg", description="[Admin] Configurează mesajul de welcome printr-un meniu")
    @app_commands.checks.has_permissions(administrator=True)
    async def setwelcomemsg(self, interaction: discord.Interaction):
        """Deschide un modal Discord pentru a configura mesajul de welcome.

        Variabile disponibile în text:
        - {user}   → mențiunea utilizatorului
        - {server} → numele serverului
        - {count}  → numărul de membri după join
        """
        modal = WelcomeMessageModal(
            title="Setează mesajul de welcome",
            setting_key="welcome_message",
            description_hint="Exemplu: Bine ai venit pe {server}, {user}! Ești al {count}-lea membru.",
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(name="setgoodbyemsg", description="[Admin] Configurează mesajul de goodbye printr-un meniu")
    @app_commands.checks.has_permissions(administrator=True)
    async def setgoodbyemsg(self, interaction: discord.Interaction):
        """Deschide un modal Discord pentru a configura mesajul de goodbye.

        Variabile disponibile în text:
        - {user}   → numele utilizatorului
        - {server} → numele serverului
        """
        modal = WelcomeMessageModal(
            title="Setează mesajul de goodbye",
            setting_key="goodbye_message",
            description_hint="Exemplu: {user} a părăsit {server}. Ne vedem data viitoare!",
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(name="testwelcome", description="[Admin] Testează mesajul de bun venit")
    @app_commands.checks.has_permissions(administrator=True)
    async def testwelcome(self, interaction: discord.Interaction):
        await self.on_member_join(interaction.user)
        await interaction.response.send_message(
            embed=success_embed("Mesaj de test trimis!"), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Welcome(bot))
