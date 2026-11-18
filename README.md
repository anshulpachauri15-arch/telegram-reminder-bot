# Telegram Reminder Bot

A personal reminder bot for two people. Code lives on GitHub, runs 24/7 for free on Railway — no server to manage.

Set reminders via Telegram chat, get pinged at the exact time, and receive a morning digest every day.

---

## How it works

The bot runs as a persistent process on Railway. It polls Telegram for new messages and uses an internal scheduler to fire reminders at the exact second and send a morning digest at your chosen time.

---

## Setup

### Step 1 — Create a Telegram bot

1. Open Telegram → search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **token** you receive (looks like `7123456789:AAF...`)

### Step 2 — Find your Telegram user IDs

**Bootstrap mode (easiest):**
1. Push the repo and deploy first (Steps 3–4 below)
2. Leave `ALLOWED_USER_IDS` blank in Railway variables — the bot allows everyone in this mode
3. Send `/start` to your bot — it replies with your user ID
4. Have your wife do the same
5. Add both IDs to the `ALLOWED_USER_IDS` variable and redeploy

**Alternative — @userinfobot:**
Both of you message **@userinfobot** on Telegram. It replies with your numeric user ID instantly.

### Step 3 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/telegram-reminder-bot.git
git push -u origin main
```

### Step 4 — Deploy on Railway

1. Go to **[railway.app](https://railway.app)** → sign in with GitHub
2. Click **New Project → Deploy from GitHub repo** → select your repo
3. Railway detects the `Dockerfile` and builds automatically
4. Go to your service → **Variables** tab → add these one by one:

| Variable | Value |
|----------|-------|
| `BOT_TOKEN` | Your token from BotFather |
| `ALLOWED_USER_IDS` | `111111111,222222222` (your IDs, comma-separated) |
| `TIMEZONE` | `Asia/Kolkata` |
| `MORNING_DIGEST_HOUR` | `8` |
| `MORNING_DIGEST_MINUTE` | `0` |

5. Railway redeploys automatically after you save variables

**That's it.** Send `/start` to your bot to test it.

---

## Persistent storage

Railway doesn't persist the filesystem between deploys by default. To keep your reminders database across deploys, add a **Railway Volume**:

1. In your Railway project → **New → Volume**
2. Mount path: `/app/data`
3. Set `DATABASE_PATH=data/reminders.db` in Variables (already the default)

Without this, reminders are lost on redeploy. Add the volume before you start using the bot seriously.

---

## Bot commands

| Command | What it does |
|---------|-------------|
| `/remind <date> <time> <message>` | Set a reminder |
| `/reminders` | List all upcoming reminders |
| `/today` | Show today's reminders |
| `/delete <id>` | Remove a reminder by ID |
| `/help` | Full usage guide |
| `/start` | Welcome message + your user ID |

### Date formats

| You type | Means |
|----------|-------|
| `today` | Today |
| `tomorrow` | Tomorrow |
| `monday` | Next Monday |
| `next friday` | The Friday after this one |
| `25/12` | 25 December |
| `25/12/2025` | 25 December 2025 |
| `2025-12-25` | ISO format |
| `dec 25` or `25 dec` | 25 December |

### Time formats

| You type | Means |
|----------|-------|
| `9am` | 09:00 |
| `3pm` | 15:00 |
| `3:30pm` | 15:30 |
| `14:00` | 14:00 |
| `noon` | 12:00 |

### Examples

```
/remind tomorrow 9am Dentist appointment
/remind 25/12 6pm Christmas dinner
/remind next monday 10:30am Quarterly review
/remind friday 8pm Movie night
```

---

## Group chat (recommended)

Using a shared group gives both of you one place for all reminders:

1. Create a Telegram group with you and your wife
2. Add the bot to the group
3. Send `/start` in the group
4. Set reminders from the group — both of you see them, reminders fire in the group
5. Morning digest arrives in the group every morning

---

## Project structure

```
├── bot.py           # Handlers, scheduler, entry point
├── config.py        # Environment config + timezone
├── database.py      # SQLite CRUD
├── date_parser.py   # Parses "tomorrow 3pm" etc.
├── requirements.txt
├── Dockerfile       # Used by Railway to build
├── Procfile         # Fallback process declaration
├── railway.json     # Railway deployment config
├── .env.example     # Template — copy to .env for local testing
└── .gitignore
```

## Local testing

```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Mac/Linux

pip install -r requirements.txt
cp .env.example .env
# edit .env with your BOT_TOKEN

python bot.py
```
