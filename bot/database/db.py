"""
database/db.py — SQLite database layer
Handles all persistent storage: users, chat history, request counts, admins.
Uses aiosqlite for async-safe reads and sqlite3 for simple sync writes at startup.
"""

import sqlite3
import time
import json
import os
import logging
from datetime import date

logger = logging.getLogger(__name__)

# Resolve the DB path from the DATABASE_URL config
def _resolve_db_path() -> str:
    from bot.config import DATABASE_URL, DATA_DIR
    if DATABASE_URL.startswith("sqlite:///"):
        raw = DATABASE_URL[len("sqlite:///"):]
        # If relative path, make it relative to DATA_DIR
        if not os.path.isabs(raw):
            return os.path.join(DATA_DIR, os.path.basename(raw))
        return raw
    return os.path.join(DATA_DIR, "chatbot.db")


DB_PATH: str = ""   # Set on first call to get_db_path()


def get_db_path() -> str:
    global DB_PATH
    if not DB_PATH:
        DB_PATH = _resolve_db_path()
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH


def init_db() -> None:
    """Create all tables if they don't exist. Called once at startup."""
    path = get_db_path()
    logger.info(f"Initialising database at {path}")
    with sqlite3.connect(path) as conn:
        conn.executescript("""
        -- Users table: tracks every user who has used the bot
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            last_seen   REAL,           -- Unix timestamp
            join_date   TEXT,           -- ISO date string YYYY-MM-DD
            total_requests INTEGER DEFAULT 0
        );

        -- Chat history: stores conversation messages per user
        CREATE TABLE IF NOT EXISTS chat_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            role        TEXT NOT NULL,  -- 'user' or 'assistant'
            content     TEXT NOT NULL,
            timestamp   REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        -- Cooldown tracking: last message timestamp per user
        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id     INTEGER PRIMARY KEY,
            last_message REAL NOT NULL
        );

        -- Rate limiting: requests per minute window per user
        CREATE TABLE IF NOT EXISTS rate_limits (
            user_id     INTEGER PRIMARY KEY,
            window_start REAL NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0
        );

        -- Admins: dynamic admin list (seeds from config)
        CREATE TABLE IF NOT EXISTS admins (
            user_id     INTEGER PRIMARY KEY,
            added_by    INTEGER,
            added_at    REAL NOT NULL
        );

        -- Daily stats cache
        CREATE TABLE IF NOT EXISTS daily_stats (
            stat_date   TEXT PRIMARY KEY,   -- YYYY-MM-DD
            new_users   INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0
        );
        """)
        conn.commit()
    logger.info("Database initialised successfully.")


def _conn() -> sqlite3.Connection:
    """Return a new sqlite3 connection with row_factory set."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# ── User Management ───────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str | None, first_name: str | None) -> bool:
    """
    Insert or update a user record.
    Returns True if this is a brand-new user (for new-user counting).
    """
    today = date.today().isoformat()
    now = time.time()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        is_new = existing is None
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, last_seen, join_date, total_requests)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                username   = excluded.username,
                first_name = excluded.first_name,
                last_seen  = excluded.last_seen
        """, (user_id, username, first_name, now, today))
        conn.commit()
        # Update daily stats for new users
        if is_new:
            conn.execute("""
                INSERT INTO daily_stats (stat_date, new_users, total_requests)
                VALUES (?, 1, 0)
                ON CONFLICT(stat_date) DO UPDATE SET new_users = new_users + 1
            """, (today,))
            conn.commit()
    return is_new


def increment_user_requests(user_id: int) -> None:
    """Increment total request count for a user and update daily stats."""
    today = date.today().isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET total_requests = total_requests + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.execute("""
            INSERT INTO daily_stats (stat_date, new_users, total_requests)
            VALUES (?, 0, 1)
            ON CONFLICT(stat_date) DO UPDATE SET total_requests = total_requests + 1
        """, (today,))
        conn.commit()


def get_all_user_ids() -> list[int]:
    """Return all registered user IDs (for broadcast)."""
    with _conn() as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
    return [r["user_id"] for r in rows]


def get_stats() -> dict:
    """Return aggregate stats for /stats command."""
    today = date.today().isoformat()
    with _conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_requests = conn.execute(
            "SELECT COALESCE(SUM(total_requests),0) FROM users"
        ).fetchone()[0]
        row = conn.execute(
            "SELECT new_users, total_requests FROM daily_stats WHERE stat_date = ?",
            (today,)
        ).fetchone()
        new_users_today = row["new_users"] if row else 0
        requests_today = row["total_requests"] if row else 0
    return {
        "total_users": total_users,
        "total_requests": total_requests,
        "new_users_today": new_users_today,
        "requests_today": requests_today,
    }


# ── Chat History ──────────────────────────────────────────────────────────────

def add_message(user_id: int, role: str, content: str) -> None:
    """Append a message to the user's history."""
    from bot.config import MAX_HISTORY
    now = time.time()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, role, content, now)
        )
        conn.commit()
        # Trim to MAX_HISTORY pairs (user + assistant = 2 rows per exchange)
        max_rows = MAX_HISTORY * 2
        conn.execute("""
            DELETE FROM chat_history
            WHERE id IN (
                SELECT id FROM chat_history
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT -1 OFFSET ?
            )
        """, (user_id, max_rows))
        conn.commit()


def get_history(user_id: int) -> list[dict]:
    """Return the conversation history for a user as a list of {role, content} dicts."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC",
            (user_id,)
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def clear_history(user_id: int) -> None:
    """Delete all chat history for a user."""
    with _conn() as conn:
        conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
        conn.commit()


# ── Cooldown ──────────────────────────────────────────────────────────────────

def check_and_update_cooldown(user_id: int, cooldown_seconds: int) -> float:
    """
    Check if user is within cooldown period.
    Returns 0.0 if OK, or remaining seconds if still cooling down.
    Updates the timestamp if allowed.
    """
    now = time.time()
    with _conn() as conn:
        row = conn.execute(
            "SELECT last_message FROM cooldowns WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            elapsed = now - row["last_message"]
            if elapsed < cooldown_seconds:
                return cooldown_seconds - elapsed   # seconds remaining
        # Update / insert last_message
        conn.execute("""
            INSERT INTO cooldowns (user_id, last_message) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_message = excluded.last_message
        """, (user_id, now))
        conn.commit()
    return 0.0


# ── Rate Limiting ─────────────────────────────────────────────────────────────

def check_rate_limit(user_id: int, max_per_minute: int) -> bool:
    """
    Returns True if request is allowed, False if rate limit exceeded.
    Resets counter every 60 seconds.
    """
    now = time.time()
    window = 60.0
    with _conn() as conn:
        row = conn.execute(
            "SELECT window_start, request_count FROM rate_limits WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if row:
            if now - row["window_start"] > window:
                # New window
                conn.execute("""
                    UPDATE rate_limits SET window_start = ?, request_count = 1
                    WHERE user_id = ?
                """, (now, user_id))
                conn.commit()
                return True
            if row["request_count"] >= max_per_minute:
                return False
            conn.execute(
                "UPDATE rate_limits SET request_count = request_count + 1 WHERE user_id = ?",
                (user_id,)
            )
        else:
            conn.execute(
                "INSERT INTO rate_limits (user_id, window_start, request_count) VALUES (?,?,1)",
                (user_id, now)
            )
        conn.commit()
    return True


# ── Admin Management ──────────────────────────────────────────────────────────

def seed_admins(admin_ids: list[int]) -> None:
    """Insert default admins from config (only if not already present)."""
    now = time.time()
    with _conn() as conn:
        for uid in admin_ids:
            conn.execute("""
                INSERT OR IGNORE INTO admins (user_id, added_by, added_at)
                VALUES (?, ?, ?)
            """, (uid, uid, now))
        conn.commit()


def get_admins() -> list[int]:
    """Return all admin user IDs."""
    with _conn() as conn:
        rows = conn.execute("SELECT user_id FROM admins").fetchall()
    return [r["user_id"] for r in rows]


def add_admin(user_id: int, added_by: int) -> bool:
    """Add a new admin. Returns False if already admin."""
    if user_id in get_admins():
        return False
    now = time.time()
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?,?,?)",
            (user_id, added_by, now)
        )
        conn.commit()
    return True


def remove_admin(user_id: int) -> bool:
    """Remove an admin. Returns False if not an admin."""
    if user_id not in get_admins():
        return False
    with _conn() as conn:
        conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        conn.commit()
    return True


def is_admin(user_id: int) -> bool:
    """Check if a user is an admin."""
    return user_id in get_admins()
