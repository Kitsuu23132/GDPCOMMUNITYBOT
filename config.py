<<<<<<< HEAD
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", 0))
GOODBYE_CHANNEL_ID = int(os.getenv("GOODBYE_CHANNEL_ID", 0))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 0))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", 0))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID", 0))
LEVEL_UP_CHANNEL_ID = int(os.getenv("LEVEL_UP_CHANNEL_ID", 0))

MUTED_ROLE_ID = int(os.getenv("MUTED_ROLE_ID", 0))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", 0))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", 0))

DAILY_COINS = int(os.getenv("DAILY_COINS", 100))
WORK_MIN = int(os.getenv("WORK_MIN", 50))
WORK_MAX = int(os.getenv("WORK_MAX", 200))

# XP settings
XP_PER_MESSAGE_MIN = 5
XP_PER_MESSAGE_MAX = 15
XP_COOLDOWN_SECONDS = 60

# Colors used in embeds
COLOR_PRIMARY   = 0x5865F2   # Discord blurple
COLOR_SUCCESS   = 0x57F287   # Green
COLOR_ERROR     = 0xED4245   # Red
COLOR_WARNING   = 0xFEE75C   # Yellow
COLOR_INFO      = 0x00B0F4   # Light blue
COLOR_ECONOMY   = 0xF1C40F   # Gold
COLOR_LEVEL     = 0xE91E63   # Pink
COLOR_FUN       = 0xFF6B35   # Orange

# Leveling thresholds – XP needed to reach each level
def xp_for_level(level: int) -> int:
    """Returns total XP required to reach `level`."""
    return 5 * (level ** 2) + 50 * level + 100

# Economy shop items
SHOP_ITEMS = {
    "vip_role":    {"name": "VIP Role",    "price": 5000,  "description": "Obții rolul VIP exclusiv"},
    "color_role":  {"name": "Color Role",  "price": 1000,  "description": "Rol colorat personalizat"},
    "nickname":    {"name": "Nickname",    "price": 500,   "description": "Schimbă-ți nickname-ul"},
    "lootbox":     {"name": "Loot Box",    "price": 200,   "description": "O cutie cu recompense random"},
    "xp_boost":    {"name": "XP Boost",    "price": 1500,  "description": "2x XP timp de 24 ore"},
}
=======
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("PREFIX", "!")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", 0))
GOODBYE_CHANNEL_ID = int(os.getenv("GOODBYE_CHANNEL_ID", 0))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", 0))
TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", 0))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID", 0))
LEVEL_UP_CHANNEL_ID = int(os.getenv("LEVEL_UP_CHANNEL_ID", 0))

MUTED_ROLE_ID = int(os.getenv("MUTED_ROLE_ID", 0))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID", 0))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", 0))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID", 0))

DAILY_COINS = int(os.getenv("DAILY_COINS", 100))
WORK_MIN = int(os.getenv("WORK_MIN", 50))
WORK_MAX = int(os.getenv("WORK_MAX", 200))

# XP settings
XP_PER_MESSAGE_MIN = 5
XP_PER_MESSAGE_MAX = 15
XP_COOLDOWN_SECONDS = 60

# Colors used in embeds
COLOR_PRIMARY   = 0x5865F2   # Discord blurple
COLOR_SUCCESS   = 0x57F287   # Green
COLOR_ERROR     = 0xED4245   # Red
COLOR_WARNING   = 0xFEE75C   # Yellow
COLOR_INFO      = 0x00B0F4   # Light blue
COLOR_ECONOMY   = 0xF1C40F   # Gold
COLOR_LEVEL     = 0xE91E63   # Pink
COLOR_FUN       = 0xFF6B35   # Orange

# Leveling thresholds – XP needed to reach each level
def xp_for_level(level: int) -> int:
    """Returns total XP required to reach `level`."""
    return 5 * (level ** 2) + 50 * level + 100

# Economy shop items
SHOP_ITEMS = {
    "vip_role":    {"name": "VIP Role",    "price": 5000,  "description": "Obții rolul VIP exclusiv"},
    "color_role":  {"name": "Color Role",  "price": 1000,  "description": "Rol colorat personalizat"},
    "nickname":    {"name": "Nickname",    "price": 500,   "description": "Schimbă-ți nickname-ul"},
    "lootbox":     {"name": "Loot Box",    "price": 200,   "description": "O cutie cu recompense random"},
    "xp_boost":    {"name": "XP Boost",    "price": 1500,  "description": "2x XP timp de 24 ore"},
}
>>>>>>> 84b633404fd2d5a084c32e7232431219eb31d7f5
