# 🎮 GDP Community Bot

Un bot Discord complex pentru comunitatea de gaming și social **GDP Community**.

---

## ✨ Funcționalități

| Modul | Comenzi |
|-------|---------|
| ⚔️ **Moderare** | Ban, Kick, Mute (Timeout), Warn, Purge, Lock, Slowmode |
| 💰 **Economie** | Balance, Daily, Work, Transfer, Rob, Shop, Buy, Inventory, Coinflip |
| ⭐ **Nivele/XP** | Rank, Leaderboard, XP automat per mesaj, Level-up messages |
| 🎉 **Fun** | 8ball, Dice, RPS, Ghicește numărul, Trivia, Meme, Joke, Poll |
| 👋 **Welcome** | Mesaje welcome/goodbye personalizabile, Auto-role la join |
| 🎫 **Tickete** | Sistem de tickete cu categorii, Claim, Close, Add/Remove users |
| 🎊 **Giveaway** | Giveaway-uri cu timer, Reroll, End manual |
| ℹ️ **Utilitar** | Help, Ping, BotInfo, ServerInfo, UserInfo, RoleInfo, Snipe |
| ⚙️ **Admin** | Setări server, Announce, Embed, Add/Remove roles, Givecoins |

---

## 🚀 Instalare

### Cerințe
- Python 3.11+
- pip

### Pași

**1. Clonează / descarcă proiectul**

**2. Instalează dependențele**
```bash
pip install -r requirements.txt
```

**3. Configurează `.env`**

Editează fișierul `.env` și completează:
```env
DISCORD_TOKEN=tokenul_tău_de_bot
GUILD_ID=id_serverului_tău
```

Poți obține token-ul de la https://discord.com/developers/applications

**4. Configurează ID-urile de canale și roluri** (opțional, le poți seta și cu comenzile `/set*`)

**5. Pornește botul**
```bash
python bot.py
```

---

## ⚙️ Configurare Discord Developer Portal

1. Mergi la https://discord.com/developers/applications
2. Creează o aplicație nouă → Add Bot
3. Activează **Privileged Gateway Intents**:
   - ✅ SERVER MEMBERS INTENT
   - ✅ MESSAGE CONTENT INTENT
   - ✅ PRESENCE INTENT
4. Generează un link de invite cu permisiunile necesare (Administrator recomandat pentru setup)

---

## 📋 Comenzi principale

### Moderare
| Comandă | Descriere |
|---------|-----------|
| `/ban @user motiv` | Banează un utilizator |
| `/kick @user motiv` | Dă kick unui utilizator |
| `/mute @user 10m motiv` | Mutează (timeout) un utilizator |
| `/warn @user motiv` | Avertizează un utilizator |
| `/warnings @user` | Afișează avertismentele |
| `/purge 10` | Șterge 10 mesaje |
| `/lock` / `/unlock` | Blochează/deblochează canalul |

### Economie
| Comandă | Descriere |
|---------|-----------|
| `/balance` | Verifică balanța |
| `/daily` | Recompensă zilnică (100 coins) |
| `/work` | Muncește pentru coins (cooldown 1h) |
| `/transfer @user 500` | Transferă coins |
| `/rob @user` | Fură coins (40% șanse) |
| `/shop` | Afișează magazinul |
| `/buy lootbox` | Cumpără un item |
| `/coinflip 100 cap` | Pariază pe cap sau pajură |

### Giveaway
```
/giveaway 1h 2 Steam Game 50 RON
```

### Setup (Admin)
```
/setwelcome #welcome
/setgoodbye #goodbye
/setlog #logs
/setlevel #level-up
/setmemrole @Membru
/ticket   → creează panoul de tickete
```

---

## 📁 Structura Proiectului

```
GDP COMMUNITY BOT/
├── bot.py              # Entry point
├── config.py           # Configurație centralizată
├── .env                # Token și ID-uri (NU partaja!)
├── requirements.txt
├── cogs/
│   ├── moderation.py   # Comenzi de moderare
│   ├── economy.py      # Sistem economie
│   ├── leveling.py     # Sistem XP/nivel
│   ├── fun.py          # Comenzi fun
│   ├── welcome.py      # Welcome/goodbye
│   ├── tickets.py      # Sistem tickete
│   ├── giveaway.py     # Sistem giveaway
│   ├── utility.py      # Comenzi utilitare
│   └── admin.py        # Comenzi admin
├── utils/
│   ├── database.py     # Toate operațiile DB
│   └── helpers.py      # Funcții helper
└── data/
    └── gdp_bot.db      # Baza de date SQLite (auto-generată)
```

---

## 💾 Persistența datelor (XP, inventar, economie)

Tot ce ține de membri (**XP / nivel**, **RDN**, **inventar shop**, **avertismente**, **tickete**, **setări server** etc.) este salvat în **SQLite** într-un singur fișier pe disc.

- **Pe PC / VPS cu disc normal:** datele **rămân** după ce oprești sau repornești botul (fișierul `data/gdp_bot.db`).
- **La hosting cu redeploy** (Railway, unele panouri): uneori **nu** se păstrează folderul proiectului — atunci trebuie un **volum persistent**.

### Variabilă de mediu `GDP_DB_PATH` (recomandat pe hosting)

Setează calea **absolută** către un fișier într-un folder care **nu** se șterge la deploy:

```env
GDP_DB_PATH=/var/persistent/gdp_bot.db
```

Pe Windows (exemplu):

```env
GDP_DB_PATH=C:\DateBot\gdp_bot.db
```

După prima pornire, copiază acolo vechiul `gdp_bot.db` dacă migrezi de pe altă mașină.

### Fișiere SQLite auxiliare

Cu modul **WAL** activat, pot apărea lângă `.db` fișierele `-wal` și `-shm` — sunt normale; **nu le șterge** cât timp botul rulează.

---

## 🔧 Personalizare

### Shop Items
Editează `SHOP_ITEMS` în `config.py` pentru a adăuga/modifica itemele din shop.

### Level Roles
Editează `LEVEL_ROLES` în `cogs/leveling.py` pentru a asigna roluri la atingerea anumitor nivele.

### Ticket Categories
Editează `TICKET_CATEGORIES` în `cogs/tickets.py` pentru a personaliza categoriile de tickete.

---

## 🛡️ Permisiuni necesare

Botul are nevoie de:
- Manage Messages, Manage Channels, Manage Roles
- Ban Members, Kick Members, Moderate Members
- Send Messages, Embed Links, Add Reactions, Read Message History
- View Channels

---

*Creat cu ❤️ pentru comunitatea GDP*
