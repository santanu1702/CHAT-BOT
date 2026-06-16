"""
main.py — Application entry point
Starts both the Telegram bot and the FastAPI web server concurrently.

Architecture:
  - A fresh asyncio event loop is created explicitly BEFORE uvicorn touches anything.
  - uvicorn runs inside that same loop as an asyncio Task (no threads needed).
  - python-telegram-bot runs as a second asyncio Task in the same loop.

Fixes applied:
  1. uvicorn plain (no [standard]) — prevents uvloop from replacing the event loop policy.
  2. asyncio.new_event_loop() called before anything — ensures a loop always exists.
  3. HTTPXRequest with raised connect/read timeouts — fixes TimedOut on Render free tier.
  4. Polling uses read_timeout / write_timeout overrides — prevents getUpdates from timing out.
  5. Retry logic in error_handler — silently retries on transient network errors.
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
from telegram.request import HTTPXRequest

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
    """
    Build and configure the Telegram Application with all handlers.

    Key fix: HTTPXRequest is configured with generous timeouts so the bot
    doesn't crash on Render's free tier where cold-start network latency
    can easily exceed the default 5-second timeout.

      connect_timeout  — how long to wait to open a TCP connection to Telegram
      read_timeout     — how long to wait for a response (getUpdates uses long-poll)
      write_timeout    — how long to wait for a send request to complete
      pool_timeout     — how long to wait for a connection from the pool
    """
    request = HTTPXRequest(
        connect_timeout=15.0,   # seconds to establish TCP connection
        read_timeout=30.0,      # seconds to wait for data (covers long-poll)
        write_timeout=30.0,     # seconds to send a message
        pool_timeout=15.0,      # seconds to get a connection from pool
        http_version="1.1",     # HTTP/2 can cause issues on some proxied hosts
    )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)                 # <-- attach our custom HTTP client
        .get_updates_request(             # <-- separate client for getUpdates
            HTTPXRequest(
                connect_timeout=15.0,
                read_timeout=45.0,        # long-poll needs extra time
                write_timeout=15.0,
                pool_timeout=15.0,
                http_version="1.1",
            )
        )
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
    Starts both services inside a single asyncio event loop:
      1. uvicorn  — serves /health on $PORT
      2. Telegram — polls for updates

    We manually drive the Telegram Application lifecycle so we can await it
    alongside uvicorn without calling run_polling() (which creates its own loop).
    """
    uvi_config = uvicorn.Config(
        app=fastapi_app,
        host="0.0.0.0",
        port=PORT,
        log_level="warning",
        access_log=False,
        loop="none",   # use the already-running asyncio loop; don't install uvloop
    )
    uvi_server = uvicorn.Server(uvi_config)

    application = build_application()

    logger.info(f"Starting FastAPI web server on port {PORT}...")
    logger.info("Starting Telegram bot polling...")

    # ── Graceful shutdown on SIGINT / SIGTERM ──────────────────────────────────
    def _signal_handler():
        logger.info("Shutdown signal received.")
        uvi_server.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except (NotImplementedError, RuntimeError):
            pass  # Windows doesn't support add_signal_handler

    # ── Run both concurrently ──────────────────────────────────────────────────
    async with application:
        await application.start()
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
            # These override the per-request timeouts for getUpdates specifically
            read_timeout=40,
            write_timeout=30,
            connect_timeout=15,
            pool_timeout=15,
        )

        # Blocks here until uvi_server.should_exit is set
        await uvi_server.serve()

        logger.info("Stopping Telegram bot...")
        await application.updater.stop()
        await application.stop()

    logger.info("Bot stopped. Goodbye!")


# ── Synchronous entry point ───────────────────────────────────────────────────

def main() -> None:
    """
    Creates a brand-new asyncio event loop explicitly, then runs run_all().

    WHY explicit loop creation:
      On Python 3.10+ there is no implicit "current" event loop on the main thread.
      If uvicorn (even without uvloop) is imported first, asyncio.get_event_loop()
      will raise RuntimeError. We create the loop ourselves to guarantee it exists.
    """
    logger.info("=" * 60)
    logger.info("  Telegram AI Chatbot — Starting up")
    logger.info("=" * 60)

    init_db()
    seed_admins(ADMIN_IDS)
    if ADMIN_IDS:
        logger.info(f"Admin IDs seeded: {ADMIN_IDS}")
    else:
        logger.warning(
            "No ADMIN_IDS configured! Set ADMIN_IDS in your .env to enable admin commands."
        )

    # Create the event loop explicitly BEFORE anything touches asyncio internals
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(run_all())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt — shutting down.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
  
