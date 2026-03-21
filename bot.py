import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
import os
import sys
import time

import config
from utils.database import init_db

# ─── Data folder (log + DB) ──────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)

# ─── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("GDP-Bot")

# ─── Intents ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = True


# ─── Bot class ───────────────────────────────────────────────────────────────

class GDPBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.PREFIX),
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )
        self._start_time: float = time.time()
        self._frozen: bool = False
        self._frozen_reason: str = ""
        self._frozen_since = None

    async def setup_hook(self):
        log.info("Initializing database...")
        await init_db()

        cogs = [
            "cogs.moderation",
            # "cogs.economy",   # dezactivat: sistem de coins
            "cogs.leveling",
            # "cogs.fun",       # dezactivat: minigame-uri, comenzi de poze etc.
            "cogs.welcome",
            "cogs.tickets",
            "cogs.giveaway",
            "cogs.utility",
            "cogs.admin",
            "cogs.reports",
            "cogs.botcontrol",
            "cogs.music",
            "cogs.automod",
            "cogs.reaction_roles",
            # "cogs.birthday",   # dezactivat: sistem de zile de naștere
            "cogs.suggestions",
            "cogs.event_log",
            # "cogs.reminders",  # dezactivat: remindere personale
            "cogs.antiraid",
            "cogs.scheduler",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"Loaded {cog}")
            except Exception as e:
                log.error(f"Failed to load {cog}: {e}")

        log.info("Syncing slash commands...")
        try:
            # Sincronizare pe serverul tău (instant) — fără dubluri (doar guild, global gol)
            if config.GUILD_ID:
                guild = discord.Object(id=config.GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                # Șterge comenzile globale pe Discord ca să nu apară dublate în server
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
                synced = await self.tree.sync(guild=guild)
                log.info(f"Synced {len(synced)} slash commands to guild {config.GUILD_ID}")
            else:
                synced = await self.tree.sync()
                log.info(f"Synced {len(synced)} slash commands (global)")
        except Exception as e:
            log.error(f"Slash command sync failed: {e}")

    async def on_ready(self):
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{config.PREFIX}help | GDP Community"
            )
        )

    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Permisiuni insuficiente",
                    description="Nu ai permisiunile necesare pentru această comandă.",
                    color=config.COLOR_ERROR
                )
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Argumente lipsă",
                    description=f"Folosire: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`",
                    color=config.COLOR_ERROR
                )
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Argument invalid",
                    description=str(error),
                    color=config.COLOR_ERROR
                )
            )
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                embed=discord.Embed(
                    title="⏳ Cooldown activ",
                    description=f"Încearcă din nou în **{error.retry_after:.1f}s**.",
                    color=config.COLOR_WARNING
                )
            )
        else:
            log.error(f"Unhandled error in {ctx.command}: {error}", exc_info=error)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handler pentru erorile la comenzi slash."""
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="❌ Permisiuni insuficiente",
                    description="Nu ai permisiunile necesare pentru această comandă.",
                    color=config.COLOR_ERROR
                ),
                ephemeral=True
            )
            return
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="⏳ Cooldown activ",
                    description=f"Încearcă din nou în **{error.retry_after:.1f}s**.",
                    color=config.COLOR_WARNING
                ),
                ephemeral=True
            )
            return
        if interaction.response.is_done():
            try:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="❌ Eroare",
                        description=str(error)[:500],
                        color=config.COLOR_ERROR
                    ),
                    ephemeral=True
                )
            except Exception:
                pass
        else:
            try:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="❌ Eroare",
                        description=str(error)[:500],
                        color=config.COLOR_ERROR
                    ),
                    ephemeral=True
                )
            except Exception:
                pass
        log.error(f"Slash command error: {error}", exc_info=error)


# ─── Entry point ─────────────────────────────────────────────────────────────

async def main():
    if not config.TOKEN or config.TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.critical("TOKEN not set in .env file! Edit .env and add your bot token.")
        return

    bot = GDPBot()
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
