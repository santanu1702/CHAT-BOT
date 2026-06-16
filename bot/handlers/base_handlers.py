"""
handlers/base_handlers.py — Core user-facing command handlers
Handles: /start, /help, /reset, /mystats, inline keyboard callbacks
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from bot.database import upsert_user, clear_history, get_history, get_stats
from bot.utils.helpers import escape_html, main_menu_keyboard, confirm_clear_keyboard

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — Welcome message with inline keyboard."""
    user = update.effective_user
    if not user:
        return

    # Register / update user in DB
    upsert_user(user.id, user.username, user.first_name)
    logger.info(f"User {user.id} ({user.username}) started the bot.")

    name = escape_html(user.first_name or "there")
    text = (
        f"👋 Hello, <b>{name}</b>!\n\n"
        "I'm your <b>AI-powered chatbot</b> built with GPT.\n\n"
        "Just send me a message and I'll reply intelligently. "
        "I remember the last few messages so we can have a real conversation.\n\n"
        "🔹 <b>Commands:</b>\n"
        "  /start — Show this welcome screen\n"
        "  /help — Detailed help\n"
        "  /reset — Clear your conversation history\n"
        "  /mystats — Your personal usage stats\n\n"
        "Start chatting below! 👇"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — Detailed help text."""
    text = (
        "🤖 <b>AI Chatbot — Help</b>\n\n"
        "<b>How to chat:</b>\n"
        "Simply type any message and I'll respond using AI.\n\n"
        "<b>Commands:</b>\n"
        "  /start — Welcome screen\n"
        "  /help — This help message\n"
        "  /reset — Clear your conversation history\n"
        "  /mystats — View your usage statistics\n\n"
        "<b>Limits:</b>\n"
        "  • <b>Cooldown:</b> 5 seconds between messages\n"
        "  • <b>Rate limit:</b> 15 messages per minute\n"
        "  • <b>History:</b> Last 10 exchanges remembered\n\n"
        "<b>Tips:</b>\n"
        "  • Be specific and clear for better answers\n"
        "  • Use /reset to start a fresh conversation\n"
        "  • The bot remembers context within a session"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reset — Ask for confirmation before clearing history."""
    await update.message.reply_text(
        "🗑️ Are you sure you want to <b>clear your conversation history</b>?\n\n"
        "This cannot be undone.",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_clear_keyboard(),
    )


async def mystats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/mystats — Show personal usage statistics."""
    user = update.effective_user
    if not user:
        return
    from bot.database.db import _conn
    with _conn() as conn:
        row = conn.execute(
            "SELECT total_requests, join_date FROM users WHERE user_id = ?",
            (user.id,)
        ).fetchone()
    history = get_history(user.id)
    msg_count = len(history)

    if row:
        text = (
            f"📊 <b>Your Stats</b>\n\n"
            f"👤 Name: <b>{escape_html(user.first_name or 'Unknown')}</b>\n"
            f"🆔 User ID: <code>{user.id}</code>\n"
            f"📅 Joined: <b>{row['join_date']}</b>\n"
            f"📨 Total requests: <b>{row['total_requests']}</b>\n"
            f"💬 Messages in memory: <b>{msg_count}</b>"
        )
    else:
        text = "⚠️ No stats found. Send a message first!"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ── Inline Keyboard Callback Handler ─────────────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all inline keyboard button presses."""
    query = update.callback_query
    if not query:
        return
    await query.answer()  # Remove the loading spinner

    data = query.data
    user = update.effective_user

    if data == "chat_help":
        await query.edit_message_text(
            "💬 <b>How to chat:</b>\n\n"
            "Just type any message and send it! I'll reply using AI.\n\n"
            "I remember our recent conversation, so you can refer back to previous messages.\n\n"
            "Use /reset to start fresh.",
            parse_mode=ParseMode.HTML,
        )

    elif data == "help":
        text = (
            "🤖 <b>Help</b>\n\n"
            "/start — Welcome screen\n"
            "/help — This help\n"
            "/reset — Clear history\n"
            "/mystats — Your stats\n\n"
            "Just type to chat with AI!"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    elif data == "clear_history":
        await query.edit_message_text(
            "🗑️ Are you sure you want to clear your conversation history?",
            reply_markup=confirm_clear_keyboard(),
        )

    elif data == "confirm_clear":
        clear_history(user.id)
        logger.info(f"User {user.id} cleared their history.")
        await query.edit_message_text(
            "✅ <b>History cleared!</b>\n\nYour conversation has been reset. Start fresh!",
            parse_mode=ParseMode.HTML,
        )

    elif data == "cancel":
        await query.edit_message_text("❌ Cancelled. Nothing was changed.")

    elif data == "my_stats":
        from bot.database.db import _conn
        with _conn() as conn:
            row = conn.execute(
                "SELECT total_requests, join_date FROM users WHERE user_id = ?",
                (user.id,)
            ).fetchone()
        history = get_history(user.id)
        if row:
            text = (
                f"📊 <b>Your Stats</b>\n\n"
                f"👤 {escape_html(user.first_name or 'Unknown')}\n"
                f"📅 Joined: {row['join_date']}\n"
                f"📨 Total requests: {row['total_requests']}\n"
                f"💬 Messages in memory: {len(history)}"
            )
        else:
            text = "No stats yet — send a message first!"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
