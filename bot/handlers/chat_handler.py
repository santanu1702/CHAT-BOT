"""
handlers/chat_handler.py — Main AI chat handler
Processes every regular text message, enforces cooldown/rate limits,
fetches AI response, saves history, and replies.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

from bot.config import COOLDOWN_SECONDS, RATE_LIMIT_PER_MINUTE
from bot.database import (
    upsert_user, increment_user_requests,
    add_message, get_history,
    check_and_update_cooldown, check_rate_limit,
)
from bot.utils.openai_client import get_ai_response
from bot.utils.helpers import escape_html, seconds_to_human

logger = logging.getLogger(__name__)


async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Main message handler — called for every non-command text message.

    Flow:
    1. Validate user & message
    2. Register/update user
    3. Check cooldown (anti-spam)
    4. Check rate limit (per-minute cap)
    5. Show typing indicator
    6. Fetch AI response with history
    7. Save both messages to DB
    8. Reply to user
    """
    message = update.effective_message
    user = update.effective_user

    if not message or not user or not message.text:
        return

    user_text = message.text.strip()
    user_id = user.id

    # ── 1. Register user ───────────────────────────────────────────────────────
    upsert_user(user_id, user.username, user.first_name)

    # ── 2. Cooldown check ──────────────────────────────────────────────────────
    remaining = check_and_update_cooldown(user_id, COOLDOWN_SECONDS)
    if remaining > 0:
        logger.info(f"[User {user_id}] Cooldown active — {remaining:.1f}s remaining.")
        await message.reply_text(
            f"⏳ <b>Slow down!</b>\n\n"
            f"Please wait <b>{seconds_to_human(remaining)}</b> before sending another message.",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── 3. Rate limit check ────────────────────────────────────────────────────
    if not check_rate_limit(user_id, RATE_LIMIT_PER_MINUTE):
        logger.warning(f"[User {user_id}] Rate limit exceeded.")
        await message.reply_text(
            "🚦 <b>Rate limit reached!</b>\n\n"
            f"You've sent too many messages. Please wait a minute and try again.\n"
            f"<i>Limit: {RATE_LIMIT_PER_MINUTE} messages per minute.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── 4. Typing indicator (shows "Bot is typing..." in Telegram) ─────────────
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    # ── 5. Fetch conversation history & get AI response ────────────────────────
    logger.info(f"[User {user_id}] Message: {user_text[:80]}{'...' if len(user_text) > 80 else ''}")

    history = get_history(user_id)
    ai_reply = await get_ai_response(user_id, history, user_text)

    # ── 6. Persist messages ────────────────────────────────────────────────────
    add_message(user_id, "user", user_text)
    add_message(user_id, "assistant", ai_reply)
    increment_user_requests(user_id)

    # ── 7. Send reply ──────────────────────────────────────────────────────────
    # Use HTML parse mode to avoid Telegram's strict MarkdownV2 escaping issues.
    safe_reply = escape_html(ai_reply)
    try:
        await message.reply_text(safe_reply, parse_mode=ParseMode.HTML)
    except Exception as e:
        # Fallback: send as plain text if HTML still fails somehow
        logger.error(f"[User {user_id}] Failed to send HTML reply: {e}. Sending plain text.")
        await message.reply_text(ai_reply)
