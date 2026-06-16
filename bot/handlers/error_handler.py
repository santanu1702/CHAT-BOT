"""
handlers/error_handler.py — Global error handler for the Telegram bot
Catches all unhandled exceptions and logs them with full traceback.
"""

import logging
import traceback
import html

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global error handler registered with the Application.
    Logs the error and sends a friendly message to the user if possible.
    """
    # Log the full exception with traceback
    logger.error(
        "Exception while handling an update:",
        exc_info=context.error
    )

    # Format traceback for logging
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = "".join(tb_list)
    logger.debug(f"Full traceback:\n{tb_string}")

    # Try to notify the user that something went wrong
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ <b>Oops! Something went wrong.</b>\n\n"
                "An unexpected error occurred while processing your request. "
                "Please try again in a moment.\n\n"
                "<i>If this keeps happening, try /reset to clear your history.</i>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            # If even the error message fails, just log it silently
            logger.exception("Failed to send error notification to user.")
