"""
bot/web_server.py — FastAPI web server
Required for Render.com (needs an open port) and UptimeRobot health pings.

Runs alongside the Telegram bot in a separate asyncio task.
"""

import logging
import time
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Track startup time for uptime reporting
_start_time = time.time()

# Create the FastAPI app
app = FastAPI(
    title="Telegram AI Chatbot",
    description="Health and status API for the Telegram AI Chatbot",
    version="1.0.0",
    docs_url=None,    # Disable /docs on production
    redoc_url=None,
)


@app.get("/health")
async def health_check():
    """
    Health check endpoint for UptimeRobot / Render.
    Returns 200 OK with bot status info.
    """
    uptime_seconds = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "Telegram AI Chatbot",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "uptime": f"{hours}h {minutes}m {seconds}s",
            "uptime_seconds": uptime_seconds,
        }
    )


@app.get("/")
async def root():
    """Root endpoint — confirms the service is running."""
    return JSONResponse(
        status_code=200,
        content={
            "message": "Telegram AI Chatbot is running.",
            "health": "/health",
        }
    )
