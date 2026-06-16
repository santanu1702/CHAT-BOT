"""
main.py — Application entry point
Starts both the Telegram bot and the FastAPI web server concurrently.

Architecture (fixed for Python 3.12+ / uvloop compatibility):
  - A fresh asyncio event loop is created explicitly BEFORE uvicorn touches anything.
  - uvicorn runs inside that same loop as an asyncio Task (no threads needed).
  - python-telegram-bot runs as a second asyncio Task in the same loop.
  - Both tasks are gathered and run until a stop signal is received.

Root cause of the original error:
  uvicorn[standard] pulls in uvloop, which replaces the default event-loop policy.
  On Python 3.10+ there is NO implicit "current" event loop on the main thread —
  you must create one explicitly. run_polling() called asyncio.get_event_loop()
  before any loop existed, which raised RuntimeError.
"""

import asyncio
import logging
import signal

import uvicorn
from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ── Set up logging FIRST ───────────────────────────────────────────────────────
from bot.utils.logger import setup_logging
setup_logging()

logger = logging.getLogger(__name__)

from bot.config import BOT_TOKEN, ADMIN_IDS, PORT
from bot.database import init_db, seed_admins
from bot.web_server import app as fastapi_app

# Handlers
from bot.handlers.base_handlers import (
    start_handler, help_handler, reset_handler,
    mystats_handler, callback_handler,
)
from bot.handlers.chat_handler import chat_handler
from bot.handlers.admin_handlers import (
    adminlist_handler, addadmin_handler, removeadmin_handler,
    broadcast_handler, ping_handler, stats_handler,
)
from bot.handlers.error_handler import error_handler


# ── Bot builder ───────────────────────────────────────────────────────────────

async def post_init(application: Application) -> None:
    """Register the bot's command menu shown in Telegram clients."""
    await application.bot.set_my_commands([
        BotCommand("start",       "Welcome screen"),
        BotCommand("help",        "How to use this bot"),
        BotCommand("reset",       "Clear your conversation history"),
        BotCommand("mystats",     "Your personal usage stats"),
        BotCommand("adminlist",   "List all admins [Admin]"),
        BotCommand("addadmin",    "Add an admin [Admin]"),
        BotCommand("removeadmin", "Remove an admin [Admin]"),
        BotCommand("broadcast",   "Message all users [Admin]"),
        BotCommand("ping",        "Check bot latency [Admin]"),
        BotCommand("stats",       "Bot statistics [Admin]"),
    ])
    logger.info("Bot commands registered with Telegram.")


def build_application() -> Application:
    """Build and configure the Telegram Application with all handlers."""
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # User commands
    application.add_handler(CommandHandler("start",       start_handler))
    application.add_handler(CommandHandler("help",        help_handler))
    application.add_handler(CommandHandler("reset",       reset_handler))
    application.add_handler(CommandHandler("mystats",     mystats_handler))

    # Admin commands
    application.add_handler(CommandHandler("adminlist",   adminlist_handler))
    application.add_handler(CommandHandler("addadmin",    addadmin_handler))
    application.add_handler(CommandHandler("removeadmin", removeadmin_handler))
    application.add_handler(CommandHandler("broadcast",   broadcast_handler))
    application.add_handler(CommandHandler("ping",        ping_handler))
    application.add_handler(CommandHandler("stats",       stats_handler))

    # Inline keyboard callbacks
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Catch-all text messages (must be LAST)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler)
    )

    application.add_error_handler(error_handler)
    return application


# ── Async entry point ─────────────────────────────────────────────────────────

async def run_all() -> None:
    """
    Co-routine that starts both services inside a single asyncio event loop:
      1. uvicorn  — serves /health on $PORT  (asyncio-native server)
      2. Telegram — polls for updates

    We manually drive the Telegram Application lifecycle so we can await it
    alongside uvicorn without calling run_polling() (which creates its own loop).
    """
    # ── uvicorn config (no loop kwarg — it uses the running loop automatically) ─
    uvi_config = uvicorn.Config(
        app=fastapi_app,
        host="0.0.0.0",
        port=PORT,
        log_level="warning",
        access_log=False,
        # Disable uvloop/httptools workers — we're already inside asyncio
        loop="none",
    )
    uvi_server = uvicorn.Server(uvi_config)

    # ── Build Telegram application ─────────────────────────────────────────────
    application = build_application()

    logger.info(f"Starting FastAPI web server on port {PORT}...")
    logger.info("Starting Telegram bot polling...")

    # ── Graceful shutdown on SIGINT / SIGTERM ──────────────────────────────────
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received.")
        stop_event.set()
        uvi_server.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, RuntimeError):
            # Windows doesn't support add_signal_handler for all signals
            pass

    # ── Run both concurrently ──────────────────────────────────────────────────
    async with application:
        await application.start()
        # Start Telegram polling in the background
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )

        # Run uvicorn (blocks until uvi_server.should_exit is True)
        await uvi_server.serve()

        # uvicorn has exited — now stop the bot cleanly
        logger.info("Stopping Telegram bot...")
        await application.updater.stop()
        await application.stop()

    logger.info("Bot stopped. Goodbye!")


# ── Synchronous entry point ───────────────────────────────────────────────────

def main() -> None:
    """
    Creates a brand-new asyncio event loop explicitly, then runs run_all().

    WHY: On Python 3.10+ there is no implicit current loop. If uvicorn/uvloop
    is imported before we create a loop, asyncio.get_event_loop() raises
    RuntimeError. Creating the loop ourselves first avoids this entirely.
    """
    logger.info("=" * 60)
    logger.info("  Telegram AI Chatbot — Starting up")
    logger.info("=" * 60)

    # ── Database setup ─────────────────────────────────────────────────────────
    init_db()
    seed_admins(ADMIN_IDS)
    if ADMIN_IDS:
        logger.info(f"Admin IDs seeded: {ADMIN_IDS}")
    else:
        logger.warning(
            "No ADMIN_IDS configured! Set ADMIN_IDS in your .env file "
            "to enable admin commands."
        )

    # ── Create event loop explicitly (fixes uvloop RuntimeError) ──────────────
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(run_all())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
