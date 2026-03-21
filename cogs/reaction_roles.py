import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

import config
from utils import database as db
from utils.helpers import now_iso, embed, success_embed, error_embed


def make_rr_view(items: list[dict]) -> discord.ui.View:
    """Build a persistent View from rr_items rows."""
    view = discord.ui.View(timeout=None)
    for item in items:
        btn = RoleButton(
            role_id=item["role_id"],
            emoji=item["emoji"],
            label=item["label"],
            item_id=item["id"],
        )
        view.add_item(btn)
    return view


class RoleButton(discord.ui.Button):
    def __init__(self, role_id: int, emoji: str, label: str, item_id: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label,
            emoji=emoji,
            custom_id=f"rr_role_{role_id}_{item_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message(
                embed=error_embed("Rolul nu mai există pe server."), ephemeral=True
            )
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Reaction Role — eliminat")
            await interaction.response.send_message(
                embed=embed(
                    title="✅ Rol eliminat",
                    description=f"Rolul {role.mention} a fost eliminat.",
                    color=config.COLOR_ERROR
                ),
                ephemeral=True
            )
        else:
            await interaction.user.add_roles(role, reason="Reaction Role — adăugat")
            await interaction.response.send_message(
                embed=embed(
                    title="✅ Rol obținut!",
                    description=f"Ai primit rolul {role.mention}!",
                    color=config.COLOR_SUCCESS
                ),
                ephemeral=True
            )


class ReactionRoles(commands.Cog, name="Reaction Roles"):
    """Sistem de roluri prin butoane."""

    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self._load_panels())

    async def _load_panels(self):
        """Re-register all persistent views on startup."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            panels = await db.get_guild_rr_panels(guild.id)
            for panel in panels:
                items = await db.get_rr_items(panel["id"])
                if items:
                    view = make_rr_view(items)
                    self.bot.add_view(view, message_id=panel["message_id"])

    rr_group = app_commands.Group(name="rr", description="Gestionare Reaction Roles")

    # ─── /rr create ──────────────────────────────────────────────────────────

    @rr_group.command(name="create", description="Creează un panou nou de Reaction Roles")
    @app_commands.describe(
        title="Titlul panoului",
        description="Descrierea panoului (opțional)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def rr_create(self, interaction: discord.Interaction, title: str, description: str = None):
        desc = description or "Apasă un buton pentru a obține sau elimina un rol!"
        e = embed(title=f"🎭 {title}", description=desc, color=config.COLOR_PRIMARY)
        e.set_footer(text="GDP Community • Reaction Roles")

        msg = await interaction.channel.send(embed=e)
        panel_id = await db.create_rr_panel(
            interaction.guild.id, interaction.channel.id, msg.id,
            title, desc, now_iso()
        )
        await interaction.response.send_message(
            embed=success_embed(
                f"Panou **#{panel_id}** creat!\n"
                f"Acum adaugă roluri cu `/rr add {panel_id} @rol 🎮 Gamer`"
            ),
            ephemeral=True
        )

    # ─── /rr add ─────────────────────────────────────────────────────────────

    @rr_group.command(name="add", description="Adaugă un rol la un panou existent")
    @app_commands.describe(
        panel_id="ID-ul panoului (din /rr create)",
        role="Rolul de adăugat",
        emoji="Emoji pentru buton",
        label="Text pe buton"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def rr_add(self, interaction: discord.Interaction,
                      panel_id: int, role: discord.Role, emoji: str, label: str):
        panel = await db.get_rr_panel(panel_id)
        if not panel or panel["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message(
                embed=error_embed(f"Panoul #{panel_id} nu există."), ephemeral=True
            )

        items = await db.get_rr_items(panel_id)
        if len(items) >= 25:
            return await interaction.response.send_message(
                embed=error_embed("Un panou poate avea maxim 25 de roluri."), ephemeral=True
            )

        item_id = await db.add_rr_item(panel_id, interaction.guild.id, role.id, emoji, label)
        items = await db.get_rr_items(panel_id)

        # Rebuild and update message
        view = make_rr_view(items)
        self.bot.add_view(view, message_id=panel["message_id"])

        try:
            ch = interaction.guild.get_channel(panel["channel_id"])
            msg = await ch.fetch_message(panel["message_id"])

            e = embed(
                title=f"🎭 {panel['title']}",
                description=panel["description"] or "Apasă un buton pentru a obține un rol!",
                color=config.COLOR_PRIMARY,
                fields=[("🎭 Roluri disponibile",
                         "\n".join(f"{it['emoji']} **{it['label']}** → <@&{it['role_id']}>" for it in items),
                         False)]
            )
            e.set_footer(text="GDP Community • Reaction Roles")
            await msg.edit(embed=e, view=view)
        except Exception:
            pass

        await interaction.response.send_message(
            embed=success_embed(f"Rolul {role.mention} adăugat cu butonul {emoji} **{label}**.")
        )

    # ─── /rr remove ──────────────────────────────────────────────────────────

    @rr_group.command(name="remove", description="Elimină un rol dintr-un panou")
    @app_commands.describe(panel_id="ID-ul panoului", role="Rolul de eliminat")
    @app_commands.checks.has_permissions(administrator=True)
    async def rr_remove(self, interaction: discord.Interaction, panel_id: int, role: discord.Role):
        panel = await db.get_rr_panel(panel_id)
        if not panel or panel["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message(
                embed=error_embed(f"Panoul #{panel_id} nu există."), ephemeral=True
            )

        import aiosqlite
        from utils.database import DB_PATH
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "DELETE FROM rr_items WHERE panel_id=? AND role_id=?",
                (panel_id, role.id)
            )
            await conn.commit()

        items = await db.get_rr_items(panel_id)

        # Rebuild message
        try:
            ch = interaction.guild.get_channel(panel["channel_id"])
            msg = await ch.fetch_message(panel["message_id"])
            if items:
                view = make_rr_view(items)
                e = embed(
                    title=f"🎭 {panel['title']}",
                    description=panel["description"] or "",
                    color=config.COLOR_PRIMARY,
                    fields=[("🎭 Roluri disponibile",
                             "\n".join(f"{it['emoji']} **{it['label']}** → <@&{it['role_id']}>" for it in items),
                             False)]
                )
                e.set_footer(text="GDP Community • Reaction Roles")
                await msg.edit(embed=e, view=view)
            else:
                await msg.edit(view=discord.ui.View())
        except Exception:
            pass

        await interaction.response.send_message(
            embed=success_embed(f"Rolul {role.mention} eliminat din panoul #{panel_id}.")
        )

    # ─── /rr delete ──────────────────────────────────────────────────────────

    @rr_group.command(name="delete", description="Șterge un panou de Reaction Roles")
    @app_commands.describe(panel_id="ID-ul panoului")
    @app_commands.checks.has_permissions(administrator=True)
    async def rr_delete(self, interaction: discord.Interaction, panel_id: int):
        panel = await db.get_rr_panel(panel_id)
        if not panel or panel["guild_id"] != interaction.guild.id:
            return await interaction.response.send_message(
                embed=error_embed(f"Panoul #{panel_id} nu există."), ephemeral=True
            )
        try:
            ch = interaction.guild.get_channel(panel["channel_id"])
            msg = await ch.fetch_message(panel["message_id"])
            await msg.delete()
        except Exception:
            pass
        await db.delete_rr_panel(panel_id)
        await interaction.response.send_message(
            embed=success_embed(f"Panoul **#{panel_id}** șters.")
        )

    # ─── /rr list ────────────────────────────────────────────────────────────

    @rr_group.command(name="list", description="Listează toate panourile de Reaction Roles")
    @app_commands.checks.has_permissions(administrator=True)
    async def rr_list(self, interaction: discord.Interaction):
        panels = await db.get_guild_rr_panels(interaction.guild.id)
        if not panels:
            return await interaction.response.send_message(
                embed=embed(title="🎭 Reaction Roles", description="Nu există panouri create.",
                            color=config.COLOR_PRIMARY),
                ephemeral=True
            )
        lines = []
        for p in panels:
            items = await db.get_rr_items(p["id"])
            ch = interaction.guild.get_channel(p["channel_id"])
            ch_str = ch.mention if ch else "canal șters"
            lines.append(f"**#{p['id']}** — {p['title']} | {ch_str} | {len(items)} roluri")

        await interaction.response.send_message(
            embed=embed(title="🎭 Panouri Reaction Roles",
                        description="\n".join(lines),
                        color=config.COLOR_PRIMARY),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
