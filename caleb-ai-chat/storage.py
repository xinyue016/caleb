from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SAFE_USER_ID = re.compile(r"[^a-zA-Z0-9_.:@-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ChatStorage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    username_key TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_login TEXT
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user
                    ON sessions(user_id, expires_at);

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'web',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_user
                    ON messages(user_id, id DESC);

                CREATE TABLE IF NOT EXISTS webhook_events (
                    event_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def normalize_user_id(user_id: str) -> str:
        cleaned = SAFE_USER_ID.sub("_", (user_id or "guest").strip())
        return (cleaned or "guest")[:128]

    def create_user(
        self,
        user_id: str,
        username: str,
        username_key: str,
        display_name: str,
        password_hash: str,
        password_salt: str,
    ) -> dict:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users(
                    id, username, username_key, display_name,
                    password_hash, password_salt, created_at, last_login
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, username_key, display_name, password_hash, password_salt, utc_now(), utc_now()),
            )
        return self.get_user_by_id(user_id)

    def get_user_by_key(self, username_key: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username_key = ?",
                (username_key.lower().strip(),),
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def update_last_login(self, user_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE users SET last_login = ? WHERE id = ?", (utc_now(), user_id))

    def create_session(self, user_id: str, token_hash: str, expires_at: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, created_at, expires_at, last_seen) VALUES (?, ?, ?, ?, ?)",
                (token_hash, user_id, now, expires_at, now),
            )

    def get_session(self, token_hash: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    sessions.token_hash,
                    sessions.expires_at,
                    users.id,
                    users.username,
                    users.display_name,
                    users.created_at,
                    users.last_login
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE sessions SET last_seen = ? WHERE token_hash = ?",
                (utc_now(), token_hash),
            )
        return dict(row)

    def delete_session(self, token_hash: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))

    def delete_expired_sessions(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at < ?", (utc_now(),))

    def add_message(self, user_id: str, platform: str, role: str, content: str) -> None:
        user_id = self.normalize_user_id(user_id)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO messages(user_id, platform, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, platform[:24], role[:16], content[:12000], utc_now()),
            )

    def get_history(self, user_id: str, limit: int = 14) -> list[dict[str, str]]:
        user_id = self.normalize_user_id(user_id)
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM messages
                WHERE user_id = ? AND role IN ('user', 'assistant')
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, max(1, min(limit, 60))),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    def clear(self, user_id: str) -> None:
        user_id = self.normalize_user_id(user_id)
        with self.connect() as connection:
            connection.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))

    def mark_event(self, event_id: str, platform: str) -> bool:
        if not event_id:
            return True
        with self.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO webhook_events(event_id, platform, created_at) VALUES (?, ?, ?)",
                    (event_id[:256], platform[:24], utc_now()),
                )
                return True
            except sqlite3.IntegrityError:
                return False
