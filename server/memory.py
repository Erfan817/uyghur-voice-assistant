"""本地存储：会话、长期档案、失败清单、每日用量。

刻意用 SQLite 单文件：一台小机器、零运维、随时可以打包带走。
原始音频不落库（ASR 完即删），只留文本。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

from .config import DATA_DIR

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    meta TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS profile (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    text TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage (
    day TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT,
    payload TEXT,
    created_at TEXT NOT NULL
);
"""

DEFAULT_PROFILE = {
    "title": "ئاپا",
    "name": "",
    "age": "",
    "city": "乌鲁木齐",
    "health": "",
    "family": "",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | None = None) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = path or (DATA_DIR / "aynur.db")
        self._lock = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ---- 会话 ----
    def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        meta: dict | None = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, text, meta, created_at) VALUES(?,?,?,?,?)",
                (session_id, role, text, json.dumps(meta, ensure_ascii=False) if meta else None, _now()),
            )

    def recent_messages(self, session_id: str, limit: int = 8) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, text, created_at FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def message_count(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE session_id=?", (session_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    # ---- 长期档案 ----
    def get_profile(self) -> dict:
        profile = dict(DEFAULT_PROFILE)
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM profile").fetchall()
        for row in rows:
            profile[row["key"]] = row["value"] or ""
        return profile

    def set_profile(self, patch: dict) -> dict:
        with self._lock, self._connect() as conn:
            for key, value in patch.items():
                if key not in DEFAULT_PROFILE:
                    continue
                conn.execute(
                    "INSERT INTO profile(key, value, updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    (key, str(value), _now()),
                )
        return self.get_profile()

    def clear_profile(self) -> dict:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM profile")
        return self.get_profile()

    # ---- 用量 ----
    def usage_today(self) -> int:
        today = date.today().isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT count FROM usage WHERE day=?", (today,)).fetchone()
        return int(row["count"]) if row else 0

    def bump_usage(self) -> int:
        today = date.today().isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO usage(day, count) VALUES(?, 1) "
                "ON CONFLICT(day) DO UPDATE SET count = count + 1",
                (today,),
            )
            row = conn.execute("SELECT count FROM usage WHERE day=?", (today,)).fetchone()
        return int(row["count"]) if row else 1

    # ---- 失败清单 ----
    def log_failure(self, session_id: str | None, text: str, reason: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO failures(session_id, text, reason, created_at) VALUES(?,?,?,?)",
                (session_id, text, reason, _now()),
            )

    def list_failures(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT text, reason, created_at FROM failures ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ---- 事件 ----
    def log_event(self, kind: str, payload: dict | None = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO events(kind, payload, created_at) VALUES(?,?,?)",
                (kind, json.dumps(payload, ensure_ascii=False) if payload else None, _now()),
            )

    def stats(self) -> dict:
        with self._connect() as conn:
            messages = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
            failures = conn.execute("SELECT COUNT(*) AS n FROM failures").fetchone()["n"]
            events = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
        return {
            "messages": int(messages),
            "failures": int(failures),
            "events": int(events),
            "usage_today": self.usage_today(),
            "db": str(self.path),
        }
