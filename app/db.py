"""SQLite database layer for Mnemosyne Forge.

Uses aiosqlite for async access. Initializes tables on first use.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import get_app_config, get_project_root
from .oc_models import OCDraft


def _db_path() -> Path:
    cfg = get_app_config()
    return get_project_root() / cfg["database_path"]


def _get_conn() -> sqlite3.Connection:
    """Get a synchronous SQLite connection."""
    dbp = _db_path()
    dbp.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(dbp))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Initialize the database — create tables if they don't exist, run migrations."""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                draft_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                export_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS search_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                query_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                inspiration_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
        """)
        # Migration: add user_id if missing
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        if "user_id" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    finally:
        conn.close()


def create_session(session_id: str, user_id: int, title: str, draft: OCDraft, created_at: str, updated_at: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (id, user_id, title, draft_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (session_id, user_id, title, draft.model_dump_json(), created_at, updated_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(session_id: str) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["draft"] = OCDraft.model_validate_json(d.pop("draft_json"))
        return d
    finally:
        conn.close()


def list_sessions(user_id: int | None = None) -> list[dict]:
    """Return all active sessions for a user, ordered by most recently updated."""
    conn = _get_conn()
    try:
        if user_id is not None:
            rows = conn.execute(
                "SELECT id, title, status, created_at, updated_at, draft_json "
                "FROM sessions WHERE status = 'active' AND user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, status, created_at, updated_at, draft_json "
                "FROM sessions WHERE status = 'active' ORDER BY updated_at DESC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                draft = json.loads(d.pop("draft_json"))
                d["completion_score"] = draft.get("completion_score", 0)
                d["core_concept"] = draft.get("core_concept", "")
            except Exception:
                d["completion_score"] = 0
                d["core_concept"] = ""
            result.append(d)
        return result
    finally:
        conn.close()


def update_session_draft(session_id: str, draft: OCDraft) -> None:
    now_utc = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE sessions SET draft_json = ?, updated_at = ? WHERE id = ?",
            (draft.model_dump_json(), now_utc, session_id),
        )
        conn.commit()
    finally:
        conn.close()


def add_message(session_id: str, role: str, content: str, created_at: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_messages(session_id: str) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """Delete a session and its related messages + exports + search_runs. Returns True if deleted."""
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM search_runs WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM exports WHERE session_id = ?", (session_id,))
        cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def create_export_record(session_id: str, file_path: str, export_type: str) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO exports (session_id, file_path, export_type, created_at) VALUES (?, ?, ?, ?)",
            (session_id, file_path, export_type, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def update_session_title(session_id: str, title: str) -> None:
    conn = _get_conn()
    try:
        conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        conn.commit()
    finally:
        conn.close()


def insert_search_run(session_id: str, query_json: str, result_json: str, inspiration_json: str) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO search_runs (session_id, query_json, result_json, inspiration_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, query_json, result_json, inspiration_json, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_search_runs(session_id: str) -> list[dict]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM search_runs WHERE session_id = ? ORDER BY id DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
