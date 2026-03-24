import aiosqlite
import os
from datetime import datetime, timezone

import config

# Aceeași cale ca în config — un singur fișier pentru toate datele persistente
DB_PATH = config.DB_PATH


async def init_db():
    _dir = os.path.dirname(DB_PATH)
    if _dir:
        os.makedirs(_dir, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # WAL = scrieri mai sigure la crash/restart; recomandat pentru producție
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        # Economy table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                balance     INTEGER DEFAULT 0,
                bank        INTEGER DEFAULT 0,
                last_daily  TEXT    DEFAULT NULL,
                last_work   TEXT    DEFAULT NULL,
                minigames_day    TEXT DEFAULT NULL,
                minigames_played INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        """)
        # Migrații pentru DB-uri vechi (fără coloane minigame)
        try:
            await db.execute(
                "ALTER TABLE economy ADD COLUMN minigames_day TEXT DEFAULT NULL"
            )
        except aiosqlite.OperationalError:
            pass
        try:
            await db.execute(
                "ALTER TABLE economy ADD COLUMN minigames_played INTEGER DEFAULT 0"
            )
        except aiosqlite.OperationalError:
            pass
        try:
            await db.execute(
                "ALTER TABLE economy ADD COLUMN last_rob TEXT DEFAULT NULL"
            )
        except aiosqlite.OperationalError:
            pass
        try:
            await db.execute(
                "ALTER TABLE economy ADD COLUMN last_riskitall TEXT DEFAULT NULL"
            )
        except aiosqlite.OperationalError:
            pass

        # Provocări pariu 1v1 (persistă peste restart)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pvp_challenges (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                channel_id      INTEGER NOT NULL,
                message_id      INTEGER NOT NULL,
                challenger_id   INTEGER NOT NULL,
                opponent_id     INTEGER NOT NULL,
                amount          INTEGER NOT NULL,
                created_at      TEXT    NOT NULL,
                expires_at      TEXT    NOT NULL
            )
        """)

        # Leveling table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leveling (
                user_id         INTEGER NOT NULL,
                guild_id        INTEGER NOT NULL,
                xp              INTEGER DEFAULT 0,
                level           INTEGER DEFAULT 0,
                last_xp_time    TEXT    DEFAULT NULL,
                xp_boost_until  TEXT    DEFAULT NULL,
                messages        INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        """)

        # Warnings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                mod_id      INTEGER NOT NULL,
                reason      TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL
            )
        """)

        # Mutes table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                unmute_time TEXT    DEFAULT NULL,
                PRIMARY KEY (user_id, guild_id)
            )
        """)

        # Tickets table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                user_id         INTEGER NOT NULL,
                channel_id      INTEGER NOT NULL,
                status          TEXT    DEFAULT 'open',
                created_at      TEXT    NOT NULL,
                closed_at       TEXT    DEFAULT NULL,
                category        TEXT    DEFAULT 'general'
            )
        """)

        # Giveaways table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                channel_id      INTEGER NOT NULL,
                message_id      INTEGER NOT NULL,
                host_id         INTEGER NOT NULL,
                prize           TEXT    NOT NULL,
                winners_count   INTEGER DEFAULT 1,
                end_time        TEXT    NOT NULL,
                ended           INTEGER DEFAULT 0
            )
        """)

        # Reports table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id        INTEGER NOT NULL,
                reporter_id     INTEGER NOT NULL,
                reported_id     INTEGER NOT NULL,
                reason          TEXT    NOT NULL,
                evidence        TEXT    DEFAULT NULL,
                status          TEXT    DEFAULT 'pending',
                message_id      INTEGER DEFAULT NULL,
                channel_id      INTEGER DEFAULT NULL,
                handled_by      INTEGER DEFAULT NULL,
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    DEFAULT NULL
            )
        """)

        # Guild settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id            INTEGER PRIMARY KEY,
                welcome_channel     INTEGER DEFAULT 0,
                goodbye_channel     INTEGER DEFAULT 0,
                log_channel         INTEGER DEFAULT 0,
                level_channel       INTEGER DEFAULT 0,
                muted_role          INTEGER DEFAULT 0,
                member_role         INTEGER DEFAULT 0,
                report_channel      INTEGER DEFAULT 0,
                suggestion_channel  INTEGER DEFAULT 0,
                birthday_channel    INTEGER DEFAULT 0,
                welcome_message     TEXT    DEFAULT NULL,
                goodbye_message     TEXT    DEFAULT NULL
            )
        """)

        # --- Lightweight migrations for existing databases (SQLite only) ---
        # Add new columns to guild_settings if DB was created before they existed.
        try:
            await db.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN suggestion_channel INTEGER DEFAULT 0"
            )
        except aiosqlite.OperationalError:
            # Column already exists – ignore.
            pass
        try:
            await db.execute(
                "ALTER TABLE guild_settings "
                "ADD COLUMN birthday_channel INTEGER DEFAULT 0"
            )
        except aiosqlite.OperationalError:
            pass

        # Birthdays table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                day         INTEGER NOT NULL,
                month       INTEGER NOT NULL,
                birth_year  INTEGER DEFAULT NULL,
                last_wished TEXT    DEFAULT NULL,
                PRIMARY KEY (user_id, guild_id)
            )
        """)

        # Suggestions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                content     TEXT    NOT NULL,
                message_id  INTEGER DEFAULT NULL,
                channel_id  INTEGER DEFAULT NULL,
                status      TEXT    DEFAULT 'pending',
                response    TEXT    DEFAULT NULL,
                handled_by  INTEGER DEFAULT NULL,
                up_votes    INTEGER DEFAULT 0,
                down_votes  INTEGER DEFAULT 0,
                created_at  TEXT    NOT NULL
            )
        """)

        # Voice sessions (for voice XP tracking)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_sessions (
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                join_time   TEXT    NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            )
        """)

        # Reminders table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                content     TEXT    NOT NULL,
                remind_at   TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                done        INTEGER DEFAULT 0
            )
        """)

        # Scheduled messages table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                content     TEXT    DEFAULT NULL,
                embed_title TEXT    DEFAULT NULL,
                embed_desc  TEXT    DEFAULT NULL,
                embed_color TEXT    DEFAULT NULL,
                send_at     TEXT    NOT NULL,
                sent        INTEGER DEFAULT 0,
                created_by  INTEGER NOT NULL,
                repeat      TEXT    DEFAULT NULL
            )
        """)

        # Reaction role panels table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rr_panels (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                channel_id  INTEGER NOT NULL,
                message_id  INTEGER NOT NULL,
                title       TEXT    NOT NULL,
                description TEXT    DEFAULT NULL,
                created_at  TEXT    NOT NULL
            )
        """)

        # Reaction role items table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rr_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                panel_id    INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                role_id     INTEGER NOT NULL,
                emoji       TEXT    NOT NULL,
                label       TEXT    NOT NULL
            )
        """)

        # Automod config table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_config (
                guild_id            INTEGER PRIMARY KEY,
                enabled             INTEGER DEFAULT 1,
                anti_spam           INTEGER DEFAULT 1,
                spam_threshold      INTEGER DEFAULT 5,
                spam_interval       INTEGER DEFAULT 5,
                anti_links          INTEGER DEFAULT 0,
                allowed_domains     TEXT    DEFAULT NULL,
                anti_caps           INTEGER DEFAULT 1,
                caps_threshold      INTEGER DEFAULT 70,
                anti_mentions       INTEGER DEFAULT 1,
                max_mentions        INTEGER DEFAULT 5,
                bad_words           TEXT    DEFAULT NULL,
                action              TEXT    DEFAULT 'warn',
                mute_duration       INTEGER DEFAULT 300,
                log_channel         INTEGER DEFAULT 0,
                whitelist_roles     TEXT    DEFAULT NULL,
                whitelist_channels  TEXT    DEFAULT NULL
            )
        """)

        # Log channels config
        await db.execute("""
            CREATE TABLE IF NOT EXISTS log_channels (
                guild_id        INTEGER PRIMARY KEY,
                msg_delete      INTEGER DEFAULT 0,
                msg_edit        INTEGER DEFAULT 0,
                member_join     INTEGER DEFAULT 0,
                member_leave    INTEGER DEFAULT 0,
                member_ban      INTEGER DEFAULT 0,
                member_unban    INTEGER DEFAULT 0,
                role_update     INTEGER DEFAULT 0,
                voice_activity  INTEGER DEFAULT 0,
                nickname_change INTEGER DEFAULT 0,
                invite_track    INTEGER DEFAULT 0
            )
        """)

        # Anti-raid config
        await db.execute("""
            CREATE TABLE IF NOT EXISTS antiraid_config (
                guild_id        INTEGER PRIMARY KEY,
                enabled         INTEGER DEFAULT 0,
                join_threshold  INTEGER DEFAULT 10,
                join_interval   INTEGER DEFAULT 10,
                action          TEXT    DEFAULT 'lockdown',
                alert_channel   INTEGER DEFAULT 0,
                lockdown_active INTEGER DEFAULT 0
            )
        """)

        # Inventory table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                item_key    TEXT    NOT NULL,
                quantity    INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, guild_id, item_key)
            )
        """)

        # Temp voice config
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tempvoice_config (
                guild_id             INTEGER PRIMARY KEY,
                lobby_channel_id     INTEGER DEFAULT 0,
                category_id          INTEGER DEFAULT 0,
                name_template        TEXT    DEFAULT 'Canalul de voice a lui {user}',
                default_user_limit   INTEGER DEFAULT 0,
                default_bitrate      INTEGER DEFAULT 64000
            )
        """)

        # Temp voice rooms (canale create din lobby)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tempvoice_rooms (
                guild_id     INTEGER NOT NULL,
                channel_id   INTEGER PRIMARY KEY,
                owner_id     INTEGER NOT NULL,
                created_at   TEXT    NOT NULL
            )
        """)

        # Temp voice permission lists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tempvoice_whitelist (
                guild_id     INTEGER NOT NULL,
                channel_id   INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                PRIMARY KEY (guild_id, channel_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tempvoice_blacklist (
                guild_id     INTEGER NOT NULL,
                channel_id   INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                PRIMARY KEY (guild_id, channel_id, user_id)
            )
        """)

        # Sfaturi automate (tips) în chat
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tips_settings (
                guild_id         INTEGER PRIMARY KEY,
                channel_id       INTEGER DEFAULT 0,
                enabled          INTEGER DEFAULT 0,
                interval_minutes INTEGER DEFAULT 180,
                last_sent_at     TEXT    DEFAULT NULL
            )
        """)

        await db.commit()


# ─── Economy helpers ────────────────────────────────────────────────────────

async def get_economy(user_id: int, guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM economy WHERE user_id=? AND guild_id=?",
            (user_id, guild_id)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?,?)",
                (user_id, guild_id)
            )
            await db.commit()
            return {
                "balance": 0,
                "bank": 0,
                "last_daily": None,
                "last_work": None,
                "minigames_day": None,
                "minigames_played": 0,
                "last_rob": None,
                "last_riskitall": None,
            }
        d = dict(row)
        if d.get("minigames_played") is None:
            d["minigames_played"] = 0
        if "last_rob" not in d:
            d["last_rob"] = None
        if "last_riskitall" not in d:
            d["last_riskitall"] = None
        return d


async def update_balance(user_id: int, guild_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?,?)",
            (user_id, guild_id)
        )
        await db.execute(
            "UPDATE economy SET balance = balance + ? WHERE user_id=? AND guild_id=?",
            (amount, user_id, guild_id)
        )
        await db.commit()


async def set_last_daily(user_id: int, guild_id: int, timestamp: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE economy SET last_daily=? WHERE user_id=? AND guild_id=?",
            (timestamp, user_id, guild_id)
        )
        await db.commit()


async def set_last_work(user_id: int, guild_id: int, timestamp: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE economy SET last_work=? WHERE user_id=? AND guild_id=?",
            (timestamp, user_id, guild_id)
        )
        await db.commit()


async def transfer_coins(from_id: int, guild_id: int, to_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE economy SET balance = balance - ? WHERE user_id=? AND guild_id=?",
            (amount, from_id, guild_id)
        )
        await db.execute(
            "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?,?)",
            (to_id, guild_id)
        )
        await db.execute(
            "UPDATE economy SET balance = balance + ? WHERE user_id=? AND guild_id=?",
            (amount, to_id, guild_id)
        )
        await db.commit()


async def bank_deposit(user_id: int, guild_id: int, amount: int) -> bool:
    """Mută RDN din cash în bancă. Returnează False dacă nu ai destui bani."""
    if amount <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?,?)",
            (user_id, guild_id),
        )
        cur = await db.execute(
            "UPDATE economy SET balance = balance - ?, bank = bank + ? "
            "WHERE user_id=? AND guild_id=? AND balance >= ?",
            (amount, amount, user_id, guild_id, amount),
        )
        await db.commit()
        return cur.rowcount > 0


async def bank_withdraw(user_id: int, guild_id: int, amount: int) -> bool:
    """Mută RDN din bancă în cash."""
    if amount <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?,?)",
            (user_id, guild_id),
        )
        cur = await db.execute(
            "UPDATE economy SET bank = bank - ?, balance = balance + ? "
            "WHERE user_id=? AND guild_id=? AND bank >= ?",
            (amount, amount, user_id, guild_id, amount),
        )
        await db.commit()
        return cur.rowcount > 0


async def set_last_rob(user_id: int, guild_id: int, timestamp_iso: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?,?)",
            (user_id, guild_id),
        )
        await db.execute(
            "UPDATE economy SET last_rob=? WHERE user_id=? AND guild_id=?",
            (timestamp_iso, user_id, guild_id),
        )
        await db.commit()


async def set_last_riskitall(user_id: int, guild_id: int, timestamp_iso: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?,?)",
            (user_id, guild_id),
        )
        await db.execute(
            "UPDATE economy SET last_riskitall=? WHERE user_id=? AND guild_id=?",
            (timestamp_iso, user_id, guild_id),
        )
        await db.commit()


async def delete_open_pvp_challenges_between(
    guild_id: int, user_a: int, user_b: int
) -> None:
    """Evită rânduri duplicate: o nouă provocare între aceiași doi membri înlocuiește cea veche."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """DELETE FROM pvp_challenges WHERE guild_id=?
               AND ((challenger_id=? AND opponent_id=?) OR (challenger_id=? AND opponent_id=?))""",
            (guild_id, user_a, user_b, user_b, user_a),
        )
        await db.commit()


async def create_pvp_challenge(
    guild_id: int,
    channel_id: int,
    message_id: int,
    challenger_id: int,
    opponent_id: int,
    amount: int,
    created_at: str,
    expires_at: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO pvp_challenges "
            "(guild_id, channel_id, message_id, challenger_id, opponent_id, amount, created_at, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                guild_id,
                channel_id,
                message_id,
                challenger_id,
                opponent_id,
                amount,
                created_at,
                expires_at,
            ),
        )
        await db.commit()
        return cur.lastrowid


async def get_pvp_challenge(challenge_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pvp_challenges WHERE id=?",
            (challenge_id,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def get_pvp_challenge_by_message(message_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pvp_challenges WHERE message_id=? ORDER BY id DESC LIMIT 1",
            (message_id,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def delete_pvp_challenge(challenge_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pvp_challenges WHERE id=?", (challenge_id,))
        await db.commit()


async def update_pvp_challenge_message_id(challenge_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pvp_challenges SET message_id=? WHERE id=?",
            (message_id, challenge_id),
        )
        await db.commit()


async def get_economy_leaderboard(guild_id: int, limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, balance + bank AS total FROM economy WHERE guild_id=? ORDER BY total DESC LIMIT ?",
            (guild_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def try_register_minigame_play(user_id: int, guild_id: int, daily_limit: int = 5) -> bool:
    """
    Incrementează contorul minigame pentru ziua curentă (UTC).
    Returnează True dacă jocul e permis (sub limită), False dacă s-a atins limita.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?,?)",
            (user_id, guild_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT minigames_day, minigames_played FROM economy WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        ) as cur:
            row = await cur.fetchone()
        day = row["minigames_day"] if row else None
        played = (row["minigames_played"] or 0) if row else 0
        if day != today:
            played = 0
        if played >= daily_limit:
            return False
        new_played = played + 1
        await db.execute(
            "UPDATE economy SET minigames_day=?, minigames_played=? WHERE user_id=? AND guild_id=?",
            (today, new_played, user_id, guild_id),
        )
        await db.commit()
        return True


async def get_minigames_remaining(user_id: int, guild_id: int, daily_limit: int = 5) -> int:
    """Câte minigame mai poate juca utilizatorul astăzi (UTC)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = await get_economy(user_id, guild_id)
    day = data.get("minigames_day")
    played = data.get("minigames_played") or 0
    if day != today:
        played = 0
    return max(0, daily_limit - played)


# ─── Leveling helpers ────────────────────────────────────────────────────────

async def get_leveling(user_id: int, guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM leveling WHERE user_id=? AND guild_id=?",
            (user_id, guild_id)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO leveling (user_id, guild_id) VALUES (?,?)",
                (user_id, guild_id)
            )
            await db.commit()
            return {"xp": 0, "level": 0, "last_xp_time": None, "xp_boost_until": None, "messages": 0}
        return dict(row)


async def add_xp(user_id: int, guild_id: int, xp: int, messages_delta: int = 0) -> dict:
    """Add XP; messages_delta incrementează contorul doar pentru mesaje (nu pentru voice). Actualizează nivelul din XP."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT OR IGNORE INTO leveling (user_id, guild_id) VALUES (?,?)",
            (user_id, guild_id),
        )
        await db.execute(
            "UPDATE leveling SET xp = xp + ?, messages = messages + ? WHERE user_id=? AND guild_id=?",
            (xp, messages_delta, user_id, guild_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT xp, level, messages, last_xp_time, xp_boost_until FROM leveling WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        ) as cur:
            row = await cur.fetchone()
        total_xp = row["xp"]
        old_level = row["level"]
        new_level = old_level
        while total_xp >= config.xp_for_level(new_level + 1):
            new_level += 1
        if new_level != old_level:
            await db.execute(
                "UPDATE leveling SET level=? WHERE user_id=? AND guild_id=?",
                (new_level, user_id, guild_id),
            )
            await db.commit()
        out = dict(row)
        out["level"] = new_level
        out["old_level"] = old_level
        out["new_level"] = new_level
        return out


async def set_leveling_xp(user_id: int, guild_id: int, xp: int):
    """[Admin] Setează XP și recalculează nivelul după formula din config."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO leveling (user_id, guild_id) VALUES (?,?)",
            (user_id, guild_id),
        )
        new_level = 0
        while xp >= config.xp_for_level(new_level + 1):
            new_level += 1
        await db.execute(
            "UPDATE leveling SET xp=?, level=? WHERE user_id=? AND guild_id=?",
            (xp, new_level, user_id, guild_id),
        )
        await db.commit()


async def set_level(user_id: int, guild_id: int, level: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE leveling SET level=? WHERE user_id=? AND guild_id=?",
            (level, user_id, guild_id)
        )
        await db.commit()


async def update_last_xp_time(user_id: int, guild_id: int, timestamp: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE leveling SET last_xp_time=? WHERE user_id=? AND guild_id=?",
            (timestamp, user_id, guild_id)
        )
        await db.commit()


async def get_level_leaderboard(guild_id: int, limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, xp, level, messages FROM leveling WHERE guild_id=? ORDER BY xp DESC LIMIT ?",
            (guild_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─── Warnings helpers ────────────────────────────────────────────────────────

async def add_warning(user_id: int, guild_id: int, mod_id: int, reason: str, timestamp: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO warnings (user_id, guild_id, mod_id, reason, timestamp) VALUES (?,?,?,?,?)",
            (user_id, guild_id, mod_id, reason, timestamp)
        )
        await db.commit()
        return cur.lastrowid


async def get_warnings(user_id: int, guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM warnings WHERE user_id=? AND guild_id=? ORDER BY timestamp DESC",
            (user_id, guild_id)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_warning(warn_id: int, guild_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM warnings WHERE id=? AND guild_id=?",
            (warn_id, guild_id)
        )
        await db.commit()
        return cur.rowcount > 0


async def clear_warnings(user_id: int, guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warnings WHERE user_id=? AND guild_id=?",
            (user_id, guild_id)
        )
        await db.commit()


# ─── Ticket helpers ──────────────────────────────────────────────────────────

async def create_ticket(guild_id: int, user_id: int, channel_id: int, category: str, created_at: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tickets (guild_id, user_id, channel_id, status, created_at, category) VALUES (?,?,?,?,?,?)",
            (guild_id, user_id, channel_id, "open", created_at, category)
        )
        await db.commit()
        return cur.lastrowid


async def close_ticket(channel_id: int, closed_at: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tickets SET status='closed', closed_at=? WHERE channel_id=?",
            (closed_at, channel_id)
        )
        await db.commit()


async def get_ticket_by_channel(channel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tickets WHERE channel_id=?",
            (channel_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


# ─── Giveaway helpers ────────────────────────────────────────────────────────

async def create_giveaway(guild_id: int, channel_id: int, message_id: int, host_id: int,
                          prize: str, winners_count: int, end_time: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners_count, end_time) "
            "VALUES (?,?,?,?,?,?,?)",
            (guild_id, channel_id, message_id, host_id, prize, winners_count, end_time)
        )
        await db.commit()
        return cur.lastrowid


async def get_active_giveaways() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM giveaways WHERE ended=0"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def end_giveaway(giveaway_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE giveaways SET ended=1 WHERE id=?",
            (giveaway_id,)
        )
        await db.commit()


# ─── Guild settings helpers ──────────────────────────────────────────────────

async def get_guild_settings(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM guild_settings WHERE guild_id=?",
            (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()
            return {"guild_id": guild_id, "welcome_channel": 0, "goodbye_channel": 0,
                    "log_channel": 0, "level_channel": 0, "muted_role": 0, "member_role": 0,
                    "welcome_message": None, "goodbye_message": None}
        return dict(row)


async def update_guild_setting(guild_id: int, key: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
            (guild_id,)
        )
        await db.execute(
            f"UPDATE guild_settings SET {key}=? WHERE guild_id=?",
            (value, guild_id)
        )
        await db.commit()


# ─── Inventory helpers ───────────────────────────────────────────────────────

async def add_to_inventory(user_id: int, guild_id: int, item_key: str, quantity: int = 1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO inventory (user_id, guild_id, item_key, quantity) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, guild_id, item_key) DO UPDATE SET quantity = quantity + ?",
            (user_id, guild_id, item_key, quantity, quantity)
        )
        await db.commit()


async def remove_from_inventory(user_id: int, guild_id: int, item_key: str, quantity: int = 1) -> bool:
    """Scade cantitatea; șterge rândul dacă ajunge la 0. Returnează True dacă s-a putut."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT quantity FROM inventory WHERE user_id=? AND guild_id=? AND item_key=?",
            (user_id, guild_id, item_key),
        ) as cur:
            row = await cur.fetchone()
        if not row or row["quantity"] < quantity:
            return False
        new_q = row["quantity"] - quantity
        if new_q <= 0:
            await db.execute(
                "DELETE FROM inventory WHERE user_id=? AND guild_id=? AND item_key=?",
                (user_id, guild_id, item_key),
            )
        else:
            await db.execute(
                "UPDATE inventory SET quantity=? WHERE user_id=? AND guild_id=? AND item_key=?",
                (new_q, user_id, guild_id, item_key),
            )
        await db.commit()
        return True


async def get_inventory(user_id: int, guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM inventory WHERE user_id=? AND guild_id=?",
            (user_id, guild_id)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─── Reports helpers ─────────────────────────────────────────────────────────

async def create_report(guild_id: int, reporter_id: int, reported_id: int,
                        reason: str, evidence: str, created_at: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO reports (guild_id, reporter_id, reported_id, reason, evidence, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (guild_id, reporter_id, reported_id, reason, evidence, created_at)
        )
        await db.commit()
        return cur.lastrowid


async def update_report(report_id: int, status: str, handled_by: int, updated_at: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE reports SET status=?, handled_by=?, updated_at=? WHERE id=?",
            (status, handled_by, updated_at, report_id)
        )
        await db.commit()


async def set_report_message(report_id: int, message_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE reports SET message_id=?, channel_id=? WHERE id=?",
            (message_id, channel_id, report_id)
        )
        await db.commit()


async def get_report(report_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM reports WHERE id=?", (report_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def get_reports_against(user_id: int, guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reports WHERE reported_id=? AND guild_id=? ORDER BY created_at DESC",
            (user_id, guild_id)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_reports(guild_id: int, status: str = None, limit: int = 20) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            async with db.execute(
                "SELECT * FROM reports WHERE guild_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
                (guild_id, status, limit)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM reports WHERE guild_id=? ORDER BY created_at DESC LIMIT ?",
                (guild_id, limit)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


# ─── Birthday helpers ────────────────────────────────────────────────────────

async def set_birthday(user_id: int, guild_id: int, day: int, month: int, birth_year: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO birthdays (user_id, guild_id, day, month, birth_year) VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET day=?, month=?, birth_year=?",
            (user_id, guild_id, day, month, birth_year, day, month, birth_year)
        )
        await db.commit()


async def get_birthday(user_id: int, guild_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM birthdays WHERE user_id=? AND guild_id=?", (user_id, guild_id)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def get_todays_birthdays(guild_id: int, day: int, month: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM birthdays WHERE guild_id=? AND day=? AND month=?",
            (guild_id, day, month)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def update_last_wished(user_id: int, guild_id: int, date_str: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE birthdays SET last_wished=? WHERE user_id=? AND guild_id=?",
            (date_str, user_id, guild_id)
        )
        await db.commit()


async def get_upcoming_birthdays(guild_id: int, limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM birthdays WHERE guild_id=? ORDER BY month, day LIMIT ?",
            (guild_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─── Suggestion helpers ──────────────────────────────────────────────────────

async def create_suggestion(guild_id: int, user_id: int, content: str, created_at: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO suggestions (guild_id, user_id, content, created_at) VALUES (?,?,?,?)",
            (guild_id, user_id, content, created_at)
        )
        await db.commit()
        return cur.lastrowid


async def set_suggestion_message(suggestion_id: int, message_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE suggestions SET message_id=?, channel_id=? WHERE id=?",
            (message_id, channel_id, suggestion_id)
        )
        await db.commit()


async def update_suggestion(suggestion_id: int, status: str, response: str, handled_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE suggestions SET status=?, response=?, handled_by=? WHERE id=?",
            (status, response, handled_by, suggestion_id)
        )
        await db.commit()


async def update_suggestion_votes(suggestion_id: int, up: int, down: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE suggestions SET up_votes=?, down_votes=? WHERE id=?",
            (up, down, suggestion_id)
        )
        await db.commit()


async def get_suggestion(suggestion_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM suggestions WHERE id=?", (suggestion_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


# ─── Reminder helpers ────────────────────────────────────────────────────────

async def create_reminder(user_id: int, guild_id: int, channel_id: int,
                           content: str, remind_at: str, created_at: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, content, remind_at, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, guild_id, channel_id, content, remind_at, created_at)
        )
        await db.commit()
        return cur.lastrowid


async def get_due_reminders(now_iso: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminders WHERE done=0 AND remind_at <= ?", (now_iso,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_reminder_done(reminder_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))
        await db.commit()


async def get_user_reminders(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM reminders WHERE user_id=? AND done=0 ORDER BY remind_at ASC",
            (user_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_reminder(reminder_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM reminders WHERE id=? AND user_id=?", (reminder_id, user_id)
        )
        await db.commit()
        return cur.rowcount > 0


# ─── Scheduler helpers ───────────────────────────────────────────────────────

async def create_scheduled_message(guild_id: int, channel_id: int, content: str,
                                    embed_title: str, embed_desc: str, embed_color: str,
                                    send_at: str, created_by: int, repeat: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO scheduled_messages "
            "(guild_id, channel_id, content, embed_title, embed_desc, embed_color, send_at, created_by, repeat) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (guild_id, channel_id, content, embed_title, embed_desc, embed_color, send_at, created_by, repeat)
        )
        await db.commit()
        return cur.lastrowid


async def get_due_scheduled_messages(now_iso: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM scheduled_messages WHERE sent=0 AND send_at <= ?", (now_iso,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def mark_scheduled_sent(msg_id: int, next_send_at: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if next_send_at:
            await db.execute(
                "UPDATE scheduled_messages SET send_at=? WHERE id=?", (next_send_at, msg_id)
            )
        else:
            await db.execute("UPDATE scheduled_messages SET sent=1 WHERE id=?", (msg_id,))
        await db.commit()


async def get_guild_scheduled_messages(guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM scheduled_messages WHERE guild_id=? AND sent=0 ORDER BY send_at ASC",
            (guild_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_scheduled_message(msg_id: int, guild_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM scheduled_messages WHERE id=? AND guild_id=?", (msg_id, guild_id)
        )
        await db.commit()
        return cur.rowcount > 0


# ─── Reaction roles helpers ──────────────────────────────────────────────────

async def create_rr_panel(guild_id: int, channel_id: int, message_id: int,
                           title: str, description: str, created_at: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO rr_panels (guild_id, channel_id, message_id, title, description, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (guild_id, channel_id, message_id, title, description, created_at)
        )
        await db.commit()
        return cur.lastrowid


async def add_rr_item(panel_id: int, guild_id: int, role_id: int, emoji: str, label: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO rr_items (panel_id, guild_id, role_id, emoji, label) VALUES (?,?,?,?,?)",
            (panel_id, guild_id, role_id, emoji, label)
        )
        await db.commit()
        return cur.lastrowid


async def get_rr_panel(panel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rr_panels WHERE id=?", (panel_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def get_rr_items(panel_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM rr_items WHERE panel_id=?", (panel_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_rr_panel_by_message(message_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM rr_panels WHERE message_id=?", (message_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def get_guild_rr_panels(guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM rr_panels WHERE guild_id=?", (guild_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_rr_panel(panel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM rr_items WHERE panel_id=?", (panel_id,))
        await db.execute("DELETE FROM rr_panels WHERE id=?", (panel_id,))
        await db.commit()


async def update_rr_panel_message(panel_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE rr_panels SET message_id=? WHERE id=?", (message_id, panel_id)
        )
        await db.commit()


# ─── Automod helpers ─────────────────────────────────────────────────────────

async def get_automod_config(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM automod_config WHERE guild_id=?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (guild_id,)
            )
            await db.commit()
            return {"guild_id": guild_id, "enabled": 1, "anti_spam": 1, "spam_threshold": 5,
                    "spam_interval": 5, "anti_links": 0, "allowed_domains": None,
                    "anti_caps": 1, "caps_threshold": 70, "anti_mentions": 1, "max_mentions": 5,
                    "bad_words": None, "action": "warn", "mute_duration": 300,
                    "log_channel": 0, "whitelist_roles": None, "whitelist_channels": None}
        return dict(row)


async def update_automod_config(guild_id: int, key: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (guild_id,)
        )
        await db.execute(
            f"UPDATE automod_config SET {key}=? WHERE guild_id=?", (value, guild_id)
        )
        await db.commit()


# ─── Log channels helpers ────────────────────────────────────────────────────

async def get_log_channels(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM log_channels WHERE guild_id=?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO log_channels (guild_id) VALUES (?)", (guild_id,)
            )
            await db.commit()
            return {"guild_id": guild_id, "msg_delete": 0, "msg_edit": 0,
                    "member_join": 0, "member_leave": 0, "member_ban": 0,
                    "member_unban": 0, "role_update": 0, "voice_activity": 0,
                    "nickname_change": 0, "invite_track": 0}
        return dict(row)


async def set_log_channel(guild_id: int, log_type: str, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO log_channels (guild_id) VALUES (?)", (guild_id,)
        )
        await db.execute(
            f"UPDATE log_channels SET {log_type}=? WHERE guild_id=?", (channel_id, guild_id)
        )
        await db.commit()


# ─── Anti-raid helpers ───────────────────────────────────────────────────────

async def get_antiraid_config(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM antiraid_config WHERE guild_id=?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO antiraid_config (guild_id) VALUES (?)", (guild_id,)
            )
            await db.commit()
            return {"guild_id": guild_id, "enabled": 0, "join_threshold": 10,
                    "join_interval": 10, "action": "lockdown",
                    "alert_channel": 0, "lockdown_active": 0}
        return dict(row)


async def update_antiraid_config(guild_id: int, key: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO antiraid_config (guild_id) VALUES (?)", (guild_id,)
        )
        await db.execute(
            f"UPDATE antiraid_config SET {key}=? WHERE guild_id=?", (value, guild_id)
        )
        await db.commit()


# ─── Temp voice helpers ───────────────────────────────────────────────────────

async def get_tempvoice_config(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tempvoice_config WHERE guild_id=?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO tempvoice_config (guild_id) VALUES (?)",
                (guild_id,),
            )
            await db.commit()
            return {
                "guild_id": guild_id,
                "lobby_channel_id": 0,
                "category_id": 0,
                "name_template": "Canalul de voice a lui {user}",
                "default_user_limit": 0,
                "default_bitrate": 64000,
            }
        return dict(row)


async def update_tempvoice_config(guild_id: int, key: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO tempvoice_config (guild_id) VALUES (?)",
            (guild_id,),
        )
        await db.execute(
            f"UPDATE tempvoice_config SET {key}=? WHERE guild_id=?",
            (value, guild_id),
        )
        await db.commit()


async def upsert_tempvoice_room(guild_id: int, channel_id: int, owner_id: int, created_at: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tempvoice_rooms (guild_id, channel_id, owner_id, created_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(channel_id) DO UPDATE SET owner_id=excluded.owner_id",
            (guild_id, channel_id, owner_id, created_at),
        )
        await db.commit()


async def get_tempvoice_room(channel_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tempvoice_rooms WHERE channel_id=?", (channel_id,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def get_tempvoice_rooms_for_guild(guild_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tempvoice_rooms WHERE guild_id=?", (guild_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def set_tempvoice_owner(channel_id: int, owner_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tempvoice_rooms SET owner_id=? WHERE channel_id=?",
            (owner_id, channel_id),
        )
        await db.commit()


async def delete_tempvoice_room(channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tempvoice_rooms WHERE channel_id=?", (channel_id,))
        await db.execute("DELETE FROM tempvoice_whitelist WHERE channel_id=?", (channel_id,))
        await db.execute("DELETE FROM tempvoice_blacklist WHERE channel_id=?", (channel_id,))
        await db.commit()


async def add_tempvoice_whitelist(guild_id: int, channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO tempvoice_whitelist (guild_id, channel_id, user_id) VALUES (?,?,?)",
            (guild_id, channel_id, user_id),
        )
        await db.execute(
            "DELETE FROM tempvoice_blacklist WHERE guild_id=? AND channel_id=? AND user_id=?",
            (guild_id, channel_id, user_id),
        )
        await db.commit()


async def remove_tempvoice_whitelist(guild_id: int, channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM tempvoice_whitelist WHERE guild_id=? AND channel_id=? AND user_id=?",
            (guild_id, channel_id, user_id),
        )
        await db.commit()


async def add_tempvoice_blacklist(guild_id: int, channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO tempvoice_blacklist (guild_id, channel_id, user_id) VALUES (?,?,?)",
            (guild_id, channel_id, user_id),
        )
        await db.execute(
            "DELETE FROM tempvoice_whitelist WHERE guild_id=? AND channel_id=? AND user_id=?",
            (guild_id, channel_id, user_id),
        )
        await db.commit()


async def remove_tempvoice_blacklist(guild_id: int, channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM tempvoice_blacklist WHERE guild_id=? AND channel_id=? AND user_id=?",
            (guild_id, channel_id, user_id),
        )
        await db.commit()


async def get_tempvoice_whitelist(channel_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM tempvoice_whitelist WHERE channel_id=?", (channel_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [int(r[0]) for r in rows]


async def get_tempvoice_blacklist(channel_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM tempvoice_blacklist WHERE channel_id=?", (channel_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [int(r[0]) for r in rows]


# ─── Tips (sfaturi automate) ──────────────────────────────────────────────────

async def get_tips_settings(guild_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tips_settings WHERE guild_id=?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            default_ch = int(getattr(config, "TIPS_CHANNEL_ID", 0) or 0)
            if guild_id != int(getattr(config, "GUILD_ID", 0) or 0):
                default_ch = 0
            default_en = 1 if (getattr(config, "TIPS_ENABLED", True) and default_ch) else 0
            interval = max(15, int(getattr(config, "TIPS_INTERVAL_MINUTES", 180) or 180))
            await db.execute(
                "INSERT INTO tips_settings (guild_id, channel_id, enabled, interval_minutes, last_sent_at) "
                "VALUES (?,?,?,?,NULL)",
                (guild_id, default_ch, default_en, interval),
            )
            await db.commit()
            return {
                "guild_id": guild_id,
                "channel_id": default_ch,
                "enabled": default_en,
                "interval_minutes": interval,
                "last_sent_at": None,
            }
        return dict(row)


async def update_tips_field(guild_id: int, field: str, value):
    if field not in ("channel_id", "enabled", "interval_minutes", "last_sent_at"):
        raise ValueError("Invalid tips field")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO tips_settings (guild_id) VALUES (?)", (guild_id,)
        )
        await db.execute(
            f"UPDATE tips_settings SET {field}=? WHERE guild_id=?",
            (value, guild_id),
        )
        await db.commit()
