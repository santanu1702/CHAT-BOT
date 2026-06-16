"""
handlers/admin_handlers.py — Admin-only command handlers
Commands: /adminlist, /addadmin, /removeadmin, /broadcast, /ping, /stats

All commands check admin status before executing.
"""

import logging
import time
import asyncio
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError

from bot.database import (
    get_admins, add_admin, remove_admin, is_admin,
    get_all_user_ids, get_stats,
)
from bot.utils.helpers import escape_html, ms_label, format_code

logger = logging.getLogger(__name__)


def admin_required(func):
    """
    Decorator that blocks non-admin users from running a command.
    Sends a polite rejection message instead.
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or not is_admin(user.id):
            logger.warning(
                f"Unauthorized admin command attempt by user {user.id if user else 'unknown'}"
            )
            await update.message.reply_text(
                "🚫 <b>Access denied.</b>\n\nThis command is for admins only.",
                parse_mode=ParseMode.HTML,
            )
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ── /adminlist ─────────────────────────────────────────────────────────────────

@admin_required
async def adminlist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/adminlist — Show all current admins."""
    admin_ids = get_admins()
    if not admin_ids:
        await update.message.reply_text("No admins found in the database.")
        return

    lines = [f"👑 <b>Admin List</b> ({len(admin_ids)} total)\n"]
    for uid in admin_ids:
        lines.append(f"  • <code>{uid}</code>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── /addadmin ─────────────────────────────────────────────────────────────────

@admin_required
async def addadmin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/addadmin <user_id> — Grant admin privileges to a user."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /addadmin <code>user_id</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw = context.args[0].strip()
    if not raw.lstrip("-").isdigit():
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
        return

    target_id = int(raw)
    requester_id = update.effective_user.id

    if add_admin(target_id, requester_id):
        logger.info(f"Admin {requester_id} added admin {target_id}.")
        await update.message.reply_text(
            f"✅ User <code>{target_id}</code> is now an admin.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"⚠️ User <code>{target_id}</code> is already an admin.",
            parse_mode=ParseMode.HTML,
        )


# ── /removeadmin ──────────────────────────────────────────────────────────────

@admin_required
async def removeadmin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/removeadmin <user_id> — Revoke admin privileges."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /removeadmin <code>user_id</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw = context.args[0].strip()
    if not raw.lstrip("-").isdigit():
        await update.message.reply_text("❌ Invalid user ID.")
        return

    target_id = int(raw)
    requester_id = update.effective_user.id

    if target_id == requester_id:
        await update.message.reply_text("❌ You can't remove yourself as admin.")
        return

    if remove_admin(target_id):
        logger.info(f"Admin {requester_id} removed admin {target_id}.")
        await update.message.reply_text(
            f"✅ User <code>{target_id}</code> has been removed from admins.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"⚠️ User <code>{target_id}</code> is not an admin.",
            parse_mode=ParseMode.HTML,
        )


# ── /broadcast ────────────────────────────────────────────────────────────────

@admin_required
async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /broadcast <message> — Send a message to ALL registered users.
    Handles failures gracefully (blocked bots, deleted accounts, etc.)
    """
    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast <code>your message here</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    broadcast_text = " ".join(context.args)
    user_ids = get_all_user_ids()

    await update.message.reply_text(
        f"📢 Starting broadcast to <b>{len(user_ids)}</b> users...",
        parse_mode=ParseMode.HTML,
    )
    logger.info(f"Admin {update.effective_user.id} broadcasting to {len(user_ids)} users.")

    success = 0
    failed = 0
    formatted = (
        f"📢 <b>Broadcast Message</b>\n\n"
        f"{escape_html(broadcast_text)}"
    )

    for uid in user_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=formatted,
                parse_mode=ParseMode.HTML,
            )
            success += 1
        except TelegramError as e:
            logger.debug(f"Broadcast failed for user {uid}: {e}")
            failed += 1
        # Small delay to avoid hitting Telegram flood limits (30 msg/sec max)
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"📊 <b>Broadcast Complete</b>\n\n"
        f"✅ Sent: <b>{success}</b>\n"
        f"❌ Failed: <b>{failed}</b>",
        parse_mode=ParseMode.HTML,
    )


# ── /ping ─────────────────────────────────────────────────────────────────────

@admin_required
async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ping — Measure bot latency and API response time."""
    # Bot latency: time to send a message and receive confirmation
    t0 = time.perf_counter()
    sent = await update.message.reply_text("🏓 Pinging...")
    bot_latency_ms = (time.perf_counter() - t0) * 1000

    # API latency: a lightweight OpenAI call (we use getMe instead to avoid cost)
    t1 = time.perf_counter()
    await context.bot.get_me()
    api_latency_ms = (time.perf_counter() - t1) * 1000

    text = (
        f"🏓 <b>Pong!</b>\n\n"
        f"📡 Bot latency: {ms_label(bot_latency_ms)}\n"
        f"🔌 Telegram API: {ms_label(api_latency_ms)}\n"
        f"🕐 Server time: <code>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</code>"
    )
    await sent.edit_text(text, parse_mode=ParseMode.HTML)


# ── /stats ────────────────────────────────────────────────────────────────────

@admin_required
async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stats — Show overall bot statistics."""
    data = get_stats()
    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total users: <b>{data['total_users']}</b>\n"
        f"📨 Total requests: <b>{data['total_requests']}</b>\n"
        f"🆕 New users today: <b>{data['new_users_today']}</b>\n"
        f"⚡ Requests today: <b>{data['requests_today']}</b>\n\n"
        f"🕐 <i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</i>",
        parse_mode=ParseMode.HTML,
    )
