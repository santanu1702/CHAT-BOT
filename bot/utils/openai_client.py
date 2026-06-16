"""
utils/openai_client.py — OpenAI API wrapper
Sends chat completions using the latest openai SDK (v1+).
"""

import logging
import time
from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError

logger = logging.getLogger(__name__)

# Module-level client (created lazily on first use)
_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Return (or create) the shared AsyncOpenAI client."""
    global _client
    if _client is None:
        from bot.config import OPENAI_API_KEY
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI AsyncClient initialised.")
    return _client


async def get_ai_response(
    user_id: int,
    history: list[dict],
    user_message: str,
) -> str:
    """
    Send the conversation history + new user message to OpenAI and return the reply.

    Args:
        user_id:      Telegram user ID (for logging).
        history:      List of {'role': ..., 'content': ...} dicts (past messages).
        user_message: The new message from the user.

    Returns:
        The assistant's reply as a plain string, or an error message.
    """
    from bot.config import OPENAI_MODEL, SYSTEM_PROMPT

    client = get_openai_client()

    # Build full message list: system → history → new user message
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_message},
    ]

    logger.debug(f"[User {user_id}] Sending {len(messages)} messages to OpenAI ({OPENAI_MODEL})")
    start = time.perf_counter()

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=1024,
            temperature=0.7,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        reply = response.choices[0].message.content or "(No response)"
        logger.info(
            f"[User {user_id}] OpenAI response in {elapsed_ms:.0f}ms | "
            f"tokens: {response.usage.total_tokens if response.usage else 'N/A'}"
        )
        return reply.strip()

    except RateLimitError:
        logger.warning(f"[User {user_id}] OpenAI rate limit hit.")
        return "⚠️ The AI service is currently rate-limited. Please try again in a moment."

    except APITimeoutError:
        logger.error(f"[User {user_id}] OpenAI request timed out.")
        return "⏳ The AI took too long to respond. Please try again."

    except APIError as e:
        logger.error(f"[User {user_id}] OpenAI API error: {e}")
        return f"⚠️ AI service error: {str(e)[:200]}"

    except Exception as e:
        logger.exception(f"[User {user_id}] Unexpected error calling OpenAI: {e}")
        return "⚠️ An unexpected error occurred. Please try again later."
