"""
config.py — Central configuration loader
Reads all settings from environment variables / .env file.
"""

import os
from dotenv import load_dotenv

# Load .env file if it exists (local dev). On Render, env vars are set directly.
load_dotenv()


def _require(key: str) -> str:
    """Raise a clear error if a required env var is missing."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"❌ Missing required environment variable: {key}\n"
            f"   Copy .env.example → .env and fill in your values."
        )
    return value


# ── Required ──────────────────────────────────────────────────────────────────
BOT_TOKEN: str = _require("BOT_TOKEN")
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")

# ── Admins ────────────────────────────────────────────────────────────────────
_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(uid.strip()) for uid in _raw_admins.split(",") if uid.strip().isdigit()
]

# ── AI Settings ───────────────────────────────────────────────────────────────
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT: str = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful, friendly, and concise AI assistant. Answer clearly and accurately.",
)
MAX_HISTORY: int = int(os.getenv("MAX_HISTORY", "10"))

# ── Anti-Spam ─────────────────────────────────────────────────────────────────
COOLDOWN_SECONDS: int = int(os.getenv("COOLDOWN_SECONDS", "5"))
RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "15"))

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///bot/data/chatbot.db")

# ── Web Server ────────────────────────────────────────────────────────────────
PORT: int = int(os.getenv("PORT", "8000"))

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")

# Ensure directories exist at import time
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
