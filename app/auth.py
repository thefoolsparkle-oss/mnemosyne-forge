"""Auth module for Mnemosyne Forge.

Shares the same user database as Project Mnemosyne (忆界树).
PBKDF2-SHA256 password hashing, cookie-based sessions.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import Cookie, Depends, Header, HTTPException, Response, status

from .config import get_config

SESSION_COOKIE = "ai_chat_session"
SESSION_SECONDS = 60 * 60 * 24 * 30
GUEST_SECONDS = 60 * 60 * 24 * 3
SESSION_REFRESH_SECONDS = 60 * 60 * 24 * 7
PASSWORD_ITERATIONS = 240_000


def _auth_db_path() -> Path:
    cfg = get_config()
    shared = cfg.get("auth", {}).get("shared_db_path", "")
    if shared:
        return Path(shared)
    # Fallback: local auth DB
    from .config import get_project_root
    return get_project_root() / "data" / "auth.db"


def now_ts() -> int:
    return int(time.time())


def _dict_from_row(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


@contextmanager
def _get_db() -> Iterator[sqlite3.Connection]:
    db_path = _auth_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_auth_db() -> None:
    with _get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                is_guest INTEGER NOT NULL DEFAULT 0,
                guest_expires_at INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                nickname TEXT NOT NULL,
                avatar_url TEXT,
                gender TEXT NOT NULL DEFAULT '',
                birthday TEXT,
                signature TEXT,
                bio TEXT,
                preferences_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        """)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    guest_expires_at = int(user.get("guest_expires_at") or 0)
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user.get("role", "user"),
        "status": user["status"],
        "is_guest": bool(user.get("is_guest")),
        "guest_expires_at": guest_expires_at,
        "guest_remaining_seconds": max(0, guest_expires_at - now_ts()) if guest_expires_at else 0,
        "created_at": user["created_at"],
    }


def create_user(username: str, password: str, nickname: str | None = None) -> dict[str, Any]:
    username = username.strip()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="用户名至少需要3个字符")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码至少需要8个字符")

    ts = now_ts()
    try:
        with _get_db() as db:
            user_count = int(db.execute("SELECT COUNT(*) FROM users WHERE is_guest = 0").fetchone()[0])
            role = "admin" if user_count == 0 else "user"
            cursor = db.execute(
                "INSERT INTO users (username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (username, hash_password(password), role, ts, ts),
            )
            user_id = int(cursor.lastrowid)
            db.execute(
                "INSERT INTO user_profiles (user_id, nickname, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (user_id, nickname or username, ts, ts),
            )
            user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return _dict_from_row(user) or {}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="用户名已存在")


def create_guest_user() -> dict[str, Any]:
    ts = now_ts()
    expires_at = ts + GUEST_SECONDS
    for _ in range(5):
        username = f"guest_{secrets.token_hex(5)}"
        password = secrets.token_urlsafe(24)
        try:
            with _get_db() as db:
                cursor = db.execute(
                    "INSERT INTO users (username, password_hash, role, status, is_guest, guest_expires_at, created_at, updated_at) VALUES (?, ?, 'user', 'active', 1, ?, ?, ?)",
                    (username, hash_password(password), expires_at, ts, ts),
                )
                user_id = int(cursor.lastrowid)
                db.execute(
                    "INSERT INTO user_profiles (user_id, nickname, signature, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, "游客", "游客模式，三天后自动清除数据", ts, ts),
                )
                user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                return _dict_from_row(user) or {}
        except sqlite3.IntegrityError:
            continue
    raise HTTPException(status_code=500, detail="游客账号创建失败")


def cleanup_expired_guest_users(ts: int | None = None) -> int:
    ts = ts or now_ts()
    with _get_db() as db:
        rows = db.execute(
            "SELECT id FROM users WHERE is_guest = 1 AND guest_expires_at > 0 AND guest_expires_at <= ?",
            (ts,),
        ).fetchall()
        user_ids = [int(row["id"]) for row in rows]
        if user_ids:
            placeholders = ",".join("?" for _ in user_ids)
            db.execute(f"DELETE FROM users WHERE id IN ({placeholders})", user_ids)
    return len(user_ids)


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    cleanup_expired_guest_users()
    with _get_db() as db:
        user = _dict_from_row(
            db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        )
    if not user or user.get("status") != "active":
        return None
    if not verify_password(password, str(user["password_hash"])):
        return None
    return user


def create_session(user_id: int, max_age: int = SESSION_SECONDS) -> str:
    token = secrets.token_urlsafe(32)
    ts = now_ts()
    with _get_db() as db:
        db.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, ts, ts + max_age),
        )
    return token


def set_session_cookie(response: Response, token: str, max_age: int = SESSION_SECONDS) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, samesite="lax", path="/")


def clear_session(response: Response, token: str | None = None) -> None:
    if token:
        with _get_db() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response.delete_cookie(SESSION_COOKIE)


def _token_from_header(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def request_session_token(session_token: str | None, authorization: str | None) -> str | None:
    return _token_from_header(authorization) or session_token


def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    token = request_session_token(session_token, authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    ts = now_ts()
    cleanup_expired_guest_users(ts)
    with _get_db() as db:
        row = db.execute(
            """SELECT users.*, sessions.expires_at AS session_expires_at
               FROM sessions JOIN users ON users.id = sessions.user_id
               WHERE sessions.token = ? AND sessions.expires_at > ? AND users.status = 'active'
                 AND (users.is_guest = 0 OR users.guest_expires_at = 0 OR users.guest_expires_at > ?)""",
            (token, ts, ts),
        ).fetchone()

    user = _dict_from_row(row)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已过期")

    if not user.get("is_guest"):
        if int(user.get("session_expires_at") or 0) < ts + SESSION_REFRESH_SECONDS:
            with _get_db() as db:
                db.execute(
                    "UPDATE sessions SET expires_at = ? WHERE token = ?",
                    (ts + SESSION_SECONDS, token),
                )
    return user


def optional_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    authorization: str | None = Header(default=None),
) -> dict[str, Any] | None:
    try:
        return current_user(session_token=session_token, authorization=authorization)
    except HTTPException:
        return None


def current_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可操作")
    return user
