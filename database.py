import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from typing import Optional

from config import DATABASE_PATH, TZ


def _now() -> datetime:
    """Current local time as a naive datetime."""
    return datetime.now(TZ).replace(tzinfo=None)


def _today() -> date:
    return datetime.now(TZ).date()


def init_db():
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reminders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                chat_id    INTEGER NOT NULL,
                message    TEXT    NOT NULL,
                remind_at  TEXT    NOT NULL,
                sent       INTEGER NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS registered_chats (
                chat_id       INTEGER PRIMARY KEY,
                title         TEXT,
                registered_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def register_chat(chat_id: int, title: Optional[str] = None):
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO registered_chats (chat_id, title) VALUES (?, ?)",
            (chat_id, title),
        )


def add_reminder(user_id: int, chat_id: int, message: str, remind_at: datetime) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (user_id, chat_id, message, remind_at) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, message, remind_at.isoformat()),
        )
        return cur.lastrowid


def get_upcoming_reminders(chat_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, user_id, message, remind_at FROM reminders
               WHERE chat_id=? AND sent=0 AND remind_at >= ?
               ORDER BY remind_at""",
            (chat_id, _now().isoformat()),
        ).fetchall()
    return [dict(r) for r in rows]


def get_todays_reminders(chat_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, user_id, message, remind_at FROM reminders
               WHERE chat_id=? AND sent=0 AND date(remind_at)=?
               ORDER BY remind_at""",
            (chat_id, _today().isoformat()),
        ).fetchall()
    return [dict(r) for r in rows]


def get_due_reminders() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, user_id, chat_id, message FROM reminders WHERE sent=0 AND remind_at <= ?",
            (_now().isoformat(),),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_sent(reminder_id: int):
    with _conn() as conn:
        conn.execute("UPDATE reminders SET sent=1 WHERE id=?", (reminder_id,))


def delete_reminder(reminder_id: int, chat_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM reminders WHERE id=? AND chat_id=? AND sent=0",
            (reminder_id, chat_id),
        )
        return cur.rowcount > 0


def get_all_registered_chats() -> list[int]:
    with _conn() as conn:
        rows = conn.execute("SELECT chat_id FROM registered_chats").fetchall()
    return [r["chat_id"] for r in rows]
