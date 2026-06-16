"""
utils/helpers.py — Shared helper functions
Safe HTML escaping, message formatters, keyboard builders, etc.
"""

import html
import time
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


# ── Text Formatting ────────────────────────────────────────────────────────────

def escape_html(text: str) -> str:
    """
    Safely escape text for Telegram HTML parse mode.
    Converts <, >, &, " to their HTML entities.
    This avoids the common 'Can't parse entities' Telegram error.
    """
    return html.escape(str(text), quote=False)


def format_user_link(user_id: int, name: str) -> str:
    """Return an HTML mention link for a user."""
    safe_name = escape_html(name)
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


def format_code(text: str) -> str:
    """Wrap text in HTML <code> tags."""
    return f"<code>{escape_html(text)}</code>"


def format_bold(text: str) -> str:
    """Wrap text in HTML <b> tags."""
    return f"<b>{escape_html(text)}</b>"


# ── Keyboard Builders ─────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the main inline keyboard shown with /start."""
    keyboard = [
        [
            InlineKeyboardButton("💬 Chat with AI", callback_data="chat_help"),
            InlineKeyboardButton("🔄 Clear History", callback_data="clear_history"),
        ],
        [
            InlineKeyboardButton("ℹ️ Help", callback_data="help"),
            InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_clear_keyboard() -> InlineKeyboardMarkup:
    """Ask user to confirm clearing their history."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, clear it", callback_data="confirm_clear"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# ── Time Helpers ──────────────────────────────────────────────────────────────

def seconds_to_human(seconds: float) -> str:
    """Convert seconds to a human-readable string, e.g. '4.2s' or '1m 3s'."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m {secs}s"


def ms_label(latency_ms: float) -> str:
    """Format latency as a coloured label."""
    ms = round(latency_ms)
    if ms < 200:
        emoji = "🟢"
    elif ms < 800:
        emoji = "🟡"
    else:
        emoji = "🔴"
    return f"{emoji} {ms}ms"
