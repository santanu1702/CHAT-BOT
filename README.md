# 🤖 Telegram AI Chatbot

A production-ready Telegram chatbot powered by OpenAI GPT, built with Python 3.12, `python-telegram-bot` v20+ (async), and FastAPI. Deployable to Render.com in minutes.

---

## ✨ Features

| Feature | Details |
|---|---|
| 💬 AI Chat | GPT-powered replies with conversation memory |
| 🧠 History | Last 10 exchanges stored per user in SQLite |
| 🛡️ Anti-spam | Per-user cooldown (5s default) |
| 🚦 Rate limiting | 15 requests/minute per user |
| 👑 Admin panel | `/adminlist`, `/addadmin`, `/removeadmin`, `/broadcast`, `/ping`, `/stats` |
| 📊 Stats | User counts, request counts, daily stats |
| 📝 Logging | Rotating file logs + console output |
| 🏥 Health check | `/health` endpoint for UptimeRobot |
| ⌨️ Typing indicator | Shows "Bot is typing..." while processing |
| 🎛️ Inline keyboards | Interactive buttons for common actions |

---

## 📁 Project Structure

```
telegram-ai-bot/
├── main.py                   # Entry point — starts bot + web server
├── bot/
│   ├── config.py             # All settings (reads .env)
│   ├── web_server.py         # FastAPI server (/health endpoint)
│   ├── handlers/
│   │   ├── base_handlers.py  # /start, /help, /reset, /mystats, callbacks
│   │   ├── chat_handler.py   # Main AI chat message handler
│   │   ├── admin_handlers.py # Admin commands
│   │   └── error_handler.py  # Global error handler
│   ├── database/
│   │   └── db.py             # SQLite layer (users, history, cooldowns)
│   ├── utils/
│   │   ├── logger.py         # Logging setup (file + console)
│   │   ├── helpers.py        # HTML escaping, keyboard builders
│   │   └── openai_client.py  # OpenAI API wrapper
│   ├── data/                 # SQLite database (auto-created)
│   └── logs/                 # Log files (auto-created)
├── requirements.txt
├── Procfile                  # For Render.com
├── runtime.txt               # Python version for Render
├── .env.example              # Template for environment variables
└── .gitignore
```

---

## 🚀 Quick Start (Local)

### 1. Clone & install

```bash
git clone https://github.com/your-username/telegram-ai-bot.git
cd telegram-ai-bot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your values:
#   BOT_TOKEN=   (from @BotFather on Telegram)
#   OPENAI_API_KEY=   (from platform.openai.com)
#   ADMIN_IDS=   (your Telegram user ID — find it via @userinfobot)
```

### 3. Run

```bash
python main.py
```

The bot starts polling and the web server binds to `http://localhost:8000`.  
Visit `http://localhost:8000/health` to verify.

---

## ☁️ Deploy to Render.com

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/telegram-ai-bot.git
git push -u origin main
```

### Step 2: Create a Render Web Service

1. Go to [render.com](https://render.com) → **New → Web Service**
2. Connect your GitHub repository
3. Configure:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: Free (or Starter for always-on)

### Step 3: Set Environment Variables

In Render → your service → **Environment**, add:

| Key | Value |
|---|---|
| `BOT_TOKEN` | Your Telegram bot token |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `ADMIN_IDS` | Your Telegram user ID |
| `OPENAI_MODEL` | `gpt-4o-mini` (or `gpt-4o`) |

### Step 4: Set Up UptimeRobot (prevent Render sleep)

1. Create a free account at [uptimerobot.com](https://uptimerobot.com)
2. Add a new HTTP(S) monitor
3. URL: `https://your-app.onrender.com/health`
4. Interval: every 5 minutes

---

## 💬 Bot Commands

### User Commands
| Command | Description |
|---|---|
| `/start` | Welcome screen with inline buttons |
| `/help` | Detailed help information |
| `/reset` | Clear your conversation history |
| `/mystats` | Your personal usage statistics |

### Admin Commands
| Command | Description |
|---|---|
| `/adminlist` | Show all current admins |
| `/addadmin <id>` | Grant admin to a user |
| `/removeadmin <id>` | Revoke admin from a user |
| `/broadcast <msg>` | Send message to all users |
| `/ping` | Check bot & API latency |
| `/stats` | View global bot statistics |

---

## ⚙️ Configuration Reference

All settings are in `.env`:

```env
BOT_TOKEN=              # Required: Telegram bot token
OPENAI_API_KEY=         # Required: OpenAI API key
ADMIN_IDS=123,456       # Comma-separated admin user IDs

OPENAI_MODEL=gpt-4o-mini    # AI model (gpt-4o for best quality)
MAX_HISTORY=10              # Messages to remember per user
COOLDOWN_SECONDS=5          # Seconds between messages
RATE_LIMIT_PER_MINUTE=15    # Max messages per minute per user
PORT=8000                   # Web server port (set by Render)

SYSTEM_PROMPT=You are a helpful AI assistant.
```

---

## 🗃️ Database Schema

SQLite database at `bot/data/chatbot.db`:

- **users** — user profiles and request counts
- **chat_history** — per-user conversation messages
- **cooldowns** — last message timestamps
- **rate_limits** — per-minute request windows
- **admins** — dynamic admin list
- **daily_stats** — aggregate daily metrics

---

## 📝 Logs

Logs are written to `bot/logs/bot.log` (rotated at 5MB, 3 backups kept).

```
2024-01-15 10:23:45 [INFO    ] bot.handlers.chat_handler: [User 123456] Message: Hello!
2024-01-15 10:23:46 [INFO    ] bot.utils.openai_client: [User 123456] OpenAI response in 842ms
```

---

## 🔧 Tech Stack

- **Python 3.12**
- **python-telegram-bot 21+** — async Telegram client
- **OpenAI SDK v1+** — GPT chat completions
- **FastAPI** — lightweight web framework
- **uvicorn** — ASGI server
- **SQLite** — embedded database (zero config)
- **python-dotenv** — environment variable loading

---

## 📄 License

MIT License — free to use, modify, and deploy.
