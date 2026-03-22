import os
from dotenv import load_dotenv

load_dotenv()

# ─── Bază de date SQLite (XP, economie, inventar, tickete, setări) ───────────
# Tot ce e legat de membri este stocat în acest fișier pe disc — supraviețuiește
# restartului botului. Pe hosting (Railway, Docker etc.) setează GDP_DB_PATH către
# un volum persistent, altfel la redeploy se pierde folderul proiectului.
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DB = os.path.join(_PROJECT_ROOT, "data", "gdp_bot.db")
DB_PATH = os.path.abspath(os.getenv("GDP_DB_PATH", _DEFAULT_DB))

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

# Link-uri opționale pentru panoul /gdpanel (lasă gol dacă nu folosești)
RULES_URL = os.getenv("RULES_URL", "").strip()
INVITE_URL = os.getenv("INVITE_URL", "").strip()

DAILY_COINS = int(os.getenv("DAILY_COINS", 50))
WORK_MIN = int(os.getenv("WORK_MIN", 50))
WORK_MAX = int(os.getenv("WORK_MAX", 200))

# Monedă afișată în economie (RDN)
CURRENCY_NAME = "RDN"

# Owner(i) bot — ID-uri Discord separate prin virgulă (pentru /gaddcoins). Lasă gol = doar owner-ul aplicației din Developer Portal.
BOT_OWNER_IDS = [
    int(x.strip())
    for x in os.getenv("BOT_OWNER_IDS", "").split(",")
    if x.strip().isdigit()
]

# Minigame-uri: câte jocuri pe zi (UTC) și interval recompensă RDN
MINIGAMES_PER_DAY = int(os.getenv("MINIGAMES_PER_DAY", 5))
MINIGAME_REWARD_MIN = int(os.getenv("MINIGAME_REWARD_MIN", 5))
MINIGAME_REWARD_MAX = int(os.getenv("MINIGAME_REWARD_MAX", 45))

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

# Magazin — prețuri în RDN (chei folosite la /buy și /trade swap)
SHOP_ITEMS = {
    "vip_rank": {
        "name": "VIP Rank",
        "price": 20,
        "description": "Rang VIP permanent — canale exclusive, culori speciale, prioritate la evenimente.",
        "perks": [
            "Canale exclusive VIP",
            "Culori speciale în chat",
            "Prioritate la evenimente",
            "Badge VIP permanent",
        ],
        "tag": "POPULAR",
    },
    "veteran_rank": {
        "name": "Veteran Rank",
        "price": 40,
        "description": "Rang suprem — tot ce include VIP, plus beneficii extra.",
        "perks": [
            "Tot ce include VIP",
            "Canale secrete MVP",
            "Rol 100% personalizat",
            "Early access la update-uri",
            "Prioritate la support staff",
        ],
        "tag": "TOP TIER",
    },
    "custom_colors": {
        "name": "Culori Custom",
        "price": 5,
        "description": "Alege culoarea numelui în chat și pe profil.",
        "perks": ["Culoare personalizată", "Schimbări nelimitate", "Gradient disponibil"],
        "tag": None,
    },
    "clan_tag": {
        "name": "Clan Tag",
        "price": 15,
        "description": "Tag personalizat pentru clanul tău, vizibil în chat.",
        "perks": ["Tag unic", "Vizibil pe tot serverul", "Editabil oricând"],
        "tag": None,
    },
    "lootbox": {
        "name": "Loot Box",
        "price": 25,
        "description": "Cutie cu RDN aleatorii.",
        "perks": ["Deschide pentru surpriză"],
        "tag": None,
    },
    "xp_boost": {
        "name": "XP Boost",
        "price": 100,
        "description": "2x XP timp de 24h (activează prin ticket/staff).",
        "perks": ["Boost XP 24 ore"],
        "tag": None,
    },
}

# Roluri Discord puse/scoase automat când ai itemul în inventar (ID rol).
# Botul trebuie să aibă „Manage Roles” și rolul botului deasupra acestora.
SHOP_ITEM_ROLES = {
    "vip_rank": 1452801844928581764,
    "veteran_rank": 1452803129174134806,
    "custom_colors": 1474152163730002196,
}
