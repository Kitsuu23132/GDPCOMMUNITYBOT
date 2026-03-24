import discord
from discord.ext import commands
from discord import app_commands

import config
from utils import database as db
from utils.helpers import embed, success_embed, error_embed, now_iso


class TempVoice(commands.Cog, name="TempVoice"):
    """Canale voice temporare cu owner controls și loguri."""

    room = app_commands.Group(name="vroom", description="Control canale voice temporare")

    def __init__(self, bot):
        self.bot = bot

    async def _voice_log(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        color: int = config.COLOR_INFO,
    ):
        channels = await db.get_log_channels(guild.id)
        ch_id = channels.get("voice_activity", 0)
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch:
            return
        try:
            await ch.send(embed=embed(title=title, description=description, color=color))
        except Exception:
            pass

    async def _current_temp_room(self, interaction: discord.Interaction) -> tuple[discord.VoiceChannel | None, dict | None]:
        if not interaction.user.voice or not interaction.user.voice.channel:
            return None, None
        ch = interaction.user.voice.channel
        if not isinstance(ch, discord.VoiceChannel):
            return None, None
        room = await db.get_tempvoice_room(ch.id)
        if not room:
            return None, None
        return ch, room

    async def _is_room_owner(self, interaction: discord.Interaction, room: dict) -> bool:
        if interaction.user.id == room["owner_id"]:
            return True
        return interaction.user.guild_permissions.manage_channels

    async def _sync_room_permissions(self, channel: discord.VoiceChannel):
        wl = await db.get_tempvoice_whitelist(channel.id)
        bl = await db.get_tempvoice_blacklist(channel.id)
        guild = channel.guild
        for uid in wl:
            member = guild.get_member(uid)
            if member:
                await channel.set_permissions(member, connect=True, view_channel=True)
        for uid in bl:
            member = guild.get_member(uid)
            if member:
                await channel.set_permissions(member, connect=False, view_channel=False)

    async def _create_temp_room_for_member(self, member: discord.Member, lobby: discord.VoiceChannel):
        cfg = await db.get_tempvoice_config(member.guild.id)
        template = (cfg.get("name_template") or "Canalul de voice a lui {user}").strip()
        name = template.replace("{user}", member.display_name).replace("{username}", member.name)
        name = name[:95] if name else f"Voice a lui {member.display_name}"

        category = None
        if cfg.get("category_id"):
            cat = member.guild.get_channel(int(cfg["category_id"]))
            if isinstance(cat, discord.CategoryChannel):
                category = cat
        if category is None:
            category = lobby.category

        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
            member: discord.PermissionOverwrite(
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
                move_members=True,
                manage_channels=True,
                mute_members=True,
                deafen_members=True,
                priority_speaker=True,
            ),
        }
        if member.guild.me:
            overwrites[member.guild.me] = discord.PermissionOverwrite(
                connect=True,
                speak=True,
                move_members=True,
                manage_channels=True,
                view_channel=True,
            )

        user_limit = max(0, int(cfg.get("default_user_limit", 0) or 0))
        bitrate = int(cfg.get("default_bitrate", 64000) or 64000)
        bitrate = min(max(bitrate, 8000), member.guild.bitrate_limit)

        new_ch = await member.guild.create_voice_channel(
            name=name,
            category=category,
            user_limit=user_limit,
            bitrate=bitrate,
            overwrites=overwrites,
            reason=f"TempVoice create for {member} ({member.id})",
        )
        await db.upsert_tempvoice_room(member.guild.id, new_ch.id, member.id, now_iso())
        await self._sync_room_permissions(new_ch)
        try:
            await member.move_to(new_ch)
        except Exception:
            pass
        await self._voice_log(
            member.guild,
            "🆕 Temp Voice creat",
            f"Canal: {new_ch.mention}\nOwner: {member.mention}\nLobby: {lobby.mention}",
            config.COLOR_SUCCESS,
        )

    async def _cleanup_room_if_empty(self, channel: discord.VoiceChannel):
        room = await db.get_tempvoice_room(channel.id)
        if not room:
            return
        if len(channel.members) > 0:
            return
        guild = channel.guild
        mention = channel.mention
        try:
            await channel.delete(reason="TempVoice empty cleanup")
        except Exception:
            return
        await db.delete_tempvoice_room(channel.id)
        await self._voice_log(
            guild,
            "🗑️ Temp Voice șters",
            f"Canal șters automat (gol): {mention}",
            config.COLOR_WARNING,
        )

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            rooms = await db.get_tempvoice_rooms_for_guild(guild.id)
            for r in rooms:
                ch = guild.get_channel(r["channel_id"])
                if ch is None:
                    await db.delete_tempvoice_room(r["channel_id"])

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if isinstance(channel, discord.VoiceChannel):
            room = await db.get_tempvoice_room(channel.id)
            if room:
                await db.delete_tempvoice_room(channel.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or not member.guild:
            return

        cfg = await db.get_tempvoice_config(member.guild.id)
        lobby_id = int(cfg.get("lobby_channel_id", 0) or 0)

        # join lobby -> create room
        if after.channel and lobby_id and after.channel.id == lobby_id:
            if isinstance(after.channel, discord.VoiceChannel):
                try:
                    await self._create_temp_room_for_member(member, after.channel)
                except Exception:
                    pass
                return

        # joined a temp room while blacklisted -> kick
        if after.channel and isinstance(after.channel, discord.VoiceChannel):
            room = await db.get_tempvoice_room(after.channel.id)
            if room:
                bl = await db.get_tempvoice_blacklist(after.channel.id)
                if member.id in bl:
                    try:
                        await member.move_to(None, reason="TempVoice blacklist")
                    except Exception:
                        pass

        # left old channel -> cleanup if empty
        if before.channel and isinstance(before.channel, discord.VoiceChannel):
            await self._cleanup_room_if_empty(before.channel)

    # ─── admin setup ─────────────────────────────────────────────────────────

    @room.command(name="setup", description="[Admin] Setează canalul lobby pentru temp voice")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        lobby="Canalul voice care creează canale noi",
        category="Categoria unde se vor crea canalele (opțional)",
    )
    async def setup_cmd(
        self,
        interaction: discord.Interaction,
        lobby: discord.VoiceChannel,
        category: discord.CategoryChannel | None = None,
    ):
        await db.update_tempvoice_config(interaction.guild.id, "lobby_channel_id", lobby.id)
        await db.update_tempvoice_config(interaction.guild.id, "category_id", category.id if category else 0)
        msg = f"TempVoice activat.\nLobby: {lobby.mention}"
        if category:
            msg += f"\nCategorie: {category.mention}"
        await interaction.response.send_message(embed=success_embed(msg))

    @room.command(name="disable", description="[Admin] Dezactivează sistemul temp voice")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable_cmd(self, interaction: discord.Interaction):
        await db.update_tempvoice_config(interaction.guild.id, "lobby_channel_id", 0)
        await interaction.response.send_message(
            embed=success_embed("TempVoice dezactivat (canalele existente rămân până se golesc).")
        )

    @room.command(name="setname", description="[Admin] Schimbă template nume canal")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(template="Ex: Canalul de voice a lui {user}")
    async def setname_cmd(self, interaction: discord.Interaction, template: str):
        template = template.strip()[:100]
        if "{user}" not in template and "{username}" not in template:
            return await interaction.response.send_message(
                embed=error_embed("Template-ul trebuie să conțină `{user}` sau `{username}`."),
                ephemeral=True,
            )
        await db.update_tempvoice_config(interaction.guild.id, "name_template", template)
        await interaction.response.send_message(
            embed=success_embed(f"Template salvat: `{template}`")
        )

    @room.command(name="status", description="[Admin] Afișează status temp voice")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status_cmd(self, interaction: discord.Interaction):
        cfg = await db.get_tempvoice_config(interaction.guild.id)
        lobby = interaction.guild.get_channel(int(cfg.get("lobby_channel_id") or 0))
        cat = interaction.guild.get_channel(int(cfg.get("category_id") or 0))
        rooms = await db.get_tempvoice_rooms_for_guild(interaction.guild.id)
        await interaction.response.send_message(
            embed=embed(
                title="🔊 TempVoice status",
                color=config.COLOR_INFO,
                fields=[
                    ("Lobby", lobby.mention if lobby else "❌ Nesetat", True),
                    ("Categorie", cat.mention if cat else "Automat (categoria lobby)", True),
                    ("Canale active", str(len(rooms)), True),
                    ("Template", f"`{cfg.get('name_template')}`", False),
                ],
            ),
            ephemeral=True,
        )

    # ─── owner controls ──────────────────────────────────────────────────────

    @room.command(name="lock", description="Owner: blochează intrarea pe canal")
    async def lock_cmd(self, interaction: discord.Interaction):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        await ch.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message(embed=success_embed("Canal blocat 🔒"))
        await self._voice_log(interaction.guild, "🔒 Temp Voice lock", f"{interaction.user.mention} a blocat {ch.mention}")

    @room.command(name="unlock", description="Owner: deblochează intrarea pe canal")
    async def unlock_cmd(self, interaction: discord.Interaction):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        await ch.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message(embed=success_embed("Canal deblocat 🔓"))
        await self._voice_log(interaction.guild, "🔓 Temp Voice unlock", f"{interaction.user.mention} a deblocat {ch.mention}")

    @room.command(name="permit", description="Owner: whitelist pentru un membru")
    @app_commands.describe(member="Membrul permis")
    async def permit_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        await db.add_tempvoice_whitelist(interaction.guild.id, ch.id, member.id)
        await ch.set_permissions(member, connect=True, view_channel=True)
        await interaction.response.send_message(embed=success_embed(f"{member.mention} a fost pus pe whitelist."))
        await self._voice_log(interaction.guild, "✅ Temp Voice whitelist", f"{interaction.user.mention} a permis {member.mention} în {ch.mention}")

    @room.command(name="deny", description="Owner: blacklist pentru un membru")
    @app_commands.describe(member="Membrul blocat")
    async def deny_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        await db.add_tempvoice_blacklist(interaction.guild.id, ch.id, member.id)
        await ch.set_permissions(member, connect=False, view_channel=False)
        if member in ch.members:
            try:
                await member.move_to(None, reason="TempVoice blacklist")
            except Exception:
                pass
        await interaction.response.send_message(embed=success_embed(f"{member.mention} a fost pus pe blacklist."))
        await self._voice_log(interaction.guild, "⛔ Temp Voice blacklist", f"{interaction.user.mention} a blocat {member.mention} în {ch.mention}")

    @room.command(name="unpermit", description="Owner: scoate membru din whitelist")
    @app_commands.describe(member="Membrul")
    async def unpermit_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        await db.remove_tempvoice_whitelist(interaction.guild.id, ch.id, member.id)
        await ch.set_permissions(member, overwrite=None)
        await interaction.response.send_message(embed=success_embed(f"{member.mention} a fost scos din whitelist."))

    @room.command(name="undeny", description="Owner: scoate membru din blacklist")
    @app_commands.describe(member="Membrul")
    async def undeny_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        await db.remove_tempvoice_blacklist(interaction.guild.id, ch.id, member.id)
        await ch.set_permissions(member, overwrite=None)
        await interaction.response.send_message(embed=success_embed(f"{member.mention} a fost scos din blacklist."))

    @room.command(name="rename", description="Owner: schimbă numele canalului")
    async def rename_cmd(self, interaction: discord.Interaction, name: str):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        new_name = name.strip()[:95]
        if not new_name:
            return await interaction.response.send_message(embed=error_embed("Nume invalid."), ephemeral=True)
        old = ch.name
        await ch.edit(name=new_name, reason=f"TempVoice rename by {interaction.user}")
        await interaction.response.send_message(embed=success_embed(f"Nume schimbat: `{old}` → `{new_name}`"))
        await self._voice_log(interaction.guild, "✏️ Temp Voice rename", f"{interaction.user.mention} a redenumit {ch.mention} în `{new_name}`")

    @room.command(name="limit", description="Owner: setează limita de membri (0 = nelimitat)")
    async def limit_cmd(self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        await ch.edit(user_limit=limit)
        await interaction.response.send_message(embed=success_embed(f"Limită setată la **{limit}**."))

    @room.command(name="kick", description="Owner: scoate un membru din canal")
    async def kick_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        if member not in ch.members:
            return await interaction.response.send_message(embed=error_embed("Membrul nu este în canal."), ephemeral=True)
        try:
            await member.move_to(None, reason=f"TempVoice kick by {interaction.user}")
        except Exception as ex:
            return await interaction.response.send_message(embed=error_embed(f"Nu pot scoate membrul: {ex}"), ephemeral=True)
        await interaction.response.send_message(embed=success_embed(f"{member.mention} a fost scos din canal."))
        await self._voice_log(interaction.guild, "👢 Temp Voice kick", f"{interaction.user.mention} a scos {member.mention} din {ch.mention}")

    @room.command(name="transfer", description="Owner: transferă ownership-ul canalului")
    async def transfer_cmd(self, interaction: discord.Interaction, member: discord.Member):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if not await self._is_room_owner(interaction, room):
            return await interaction.response.send_message(embed=error_embed("Doar owner-ul canalului poate folosi comanda."), ephemeral=True)
        if member not in ch.members:
            return await interaction.response.send_message(embed=error_embed("Noul owner trebuie să fie în canal."), ephemeral=True)
        old_owner = interaction.guild.get_member(room["owner_id"])
        if old_owner:
            await ch.set_permissions(old_owner, overwrite=None)
        await ch.set_permissions(
            member,
            connect=True,
            speak=True,
            stream=True,
            use_voice_activation=True,
            move_members=True,
            manage_channels=True,
            mute_members=True,
            deafen_members=True,
            priority_speaker=True,
        )
        await db.set_tempvoice_owner(ch.id, member.id)
        await interaction.response.send_message(embed=success_embed(f"Ownership transferat către {member.mention}."))
        await self._voice_log(interaction.guild, "👑 Temp Voice transfer", f"{interaction.user.mention} a dat ownership-ul lui {member.mention} pentru {ch.mention}")

    @room.command(name="claim", description="Membru din canal: preia ownership dacă owner-ul a plecat")
    async def claim_cmd(self, interaction: discord.Interaction):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        if interaction.user.id == room["owner_id"]:
            return await interaction.response.send_message(embed=error_embed("Ești deja owner."), ephemeral=True)
        old_owner = interaction.guild.get_member(room["owner_id"])
        if old_owner and old_owner.voice and old_owner.voice.channel and old_owner.voice.channel.id == ch.id:
            return await interaction.response.send_message(embed=error_embed("Owner-ul actual este încă în canal."), ephemeral=True)
        await db.set_tempvoice_owner(ch.id, interaction.user.id)
        await ch.set_permissions(
            interaction.user,
            connect=True,
            speak=True,
            stream=True,
            use_voice_activation=True,
            move_members=True,
            manage_channels=True,
            mute_members=True,
            deafen_members=True,
            priority_speaker=True,
        )
        await interaction.response.send_message(embed=success_embed("Ai preluat ownership-ul canalului."))
        await self._voice_log(interaction.guild, "👑 Temp Voice claim", f"{interaction.user.mention} a preluat ownership-ul pentru {ch.mention}")

    @room.command(name="info", description="Afișează informații despre canalul temp voice curent")
    async def info_cmd(self, interaction: discord.Interaction):
        ch, room = await self._current_temp_room(interaction)
        if not ch or not room:
            return await interaction.response.send_message(embed=error_embed("Intră într-un canal temp voice."), ephemeral=True)
        owner = interaction.guild.get_member(room["owner_id"])
        wl = await db.get_tempvoice_whitelist(ch.id)
        bl = await db.get_tempvoice_blacklist(ch.id)
        await interaction.response.send_message(
            embed=embed(
                title="🔊 Temp Voice info",
                color=config.COLOR_INFO,
                fields=[
                    ("Canal", ch.mention, True),
                    ("Owner", owner.mention if owner else f"`{room['owner_id']}`", True),
                    ("Membri", str(len(ch.members)), True),
                    ("Limită", str(ch.user_limit or 0), True),
                    ("Whitelist", str(len(wl)), True),
                    ("Blacklist", str(len(bl)), True),
                ],
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(TempVoice(bot))
