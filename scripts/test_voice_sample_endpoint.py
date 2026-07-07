"""FastAPI endpoint test for /voice-sample ElevenLabs guard.

This test spins up the FastAPI app with TestClient, creates a real session and
voice profile, and verifies that the endpoint returns 400 when ElevenLabs is
requested without a saved voice_id.

It uses isolated test databases under data/ and does not call external APIs.
"""

from __future__ import annotations

import datetime
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app import auth, config as app_config, db
from app.oc_models import OCDraft

# Use isolated test databases so production/local auth.db is not touched.
_test_db_path = app_config.get_project_root() / "data" / "test_forge_endpoint.db"
_test_auth_path = app_config.get_project_root() / "data" / "test_auth_endpoint.db"

app_config._config_cache = {
    "app": {
        "database_path": "data/test_forge_endpoint.db",
        "export_dir": "exports",
    },
    "auth": {"shared_db_path": str(_test_auth_path)},
    "voice": {"provider": "elevenlabs"},
}

# Force auth module to re-evaluate _auth_db_path with the patched config.
auth._auth_db_cache = None

# Clean up any leftover test databases before importing the server.
_test_db_path.unlink(missing_ok=True)
_test_auth_path.unlink(missing_ok=True)

from app import server  # noqa: E402


def _admin_auth(client: TestClient) -> None:
    """Insert an admin user directly into the test auth db and set the session cookie."""
    import secrets

    ts = auth.now_ts()
    token = secrets.token_urlsafe(32)
    with auth._get_db() as conn:
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM users")
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role, status, is_guest, guest_expires_at, created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', 0, 0, ?, ?)",
            ("admin_test", auth.hash_password("password123"), "admin", ts, ts),
        )
        user_id = int(cursor.lastrowid)
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, ts, ts + auth.SESSION_SECONDS),
        )
    client.cookies.set(auth.SESSION_COOKIE, token)


def _create_session(_client: TestClient) -> str:
    # Bypass LLM-dependent session creation and insert a session row directly.
    session_id = f"voice_guard_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    draft = OCDraft(
        name="Voice Guard Test",
        core_concept="a test character for voice guard",
    )
    db.create_session(session_id, 0, "voice guard test", draft, now, now)
    return session_id


def test_voice_sample_blocks_elevenlabs_without_voice_id() -> None:
    with TestClient(server.app) as client:
        _admin_auth(client)
        session_id = _create_session(client)

        # Save a voice profile without elevenlabs_voice_id.
        db.save_voice_profile(session_id, json.dumps({"sample_text": "你好。"}))

        resp = client.post(
            f"/api/sessions/{session_id}/voice-sample",
            json={"provider": "elevenlabs"},
        )
        assert resp.status_code == 400, f"expected 400, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "专属音色" in detail or "voice_id" in detail.lower(), detail


def test_voice_sample_allows_edge_tts_without_voice_id() -> None:
    with TestClient(server.app) as client:
        _admin_auth(client)
        session_id = _create_session(client)

        db.save_voice_profile(session_id, json.dumps({"sample_text": "你好。"}))

        # Edge TTS does not require a saved voice_id and should not be blocked by the
        # ElevenLabs guard. It may succeed locally or fail for network reasons, but it
        # must not return the 400 guard error.
        resp = client.post(
            f"/api/sessions/{session_id}/voice-sample",
            json={"provider": "edge_tts"},
        )
        assert resp.status_code != 400
        body = resp.json()
        assert "专属音色" not in (body.get("detail") or body.get("error") or "")


def test_voice_sample_allows_elevenlabs_with_voice_id() -> None:
    with TestClient(server.app) as client:
        _admin_auth(client)
        session_id = _create_session(client)

        db.save_voice_profile(
            session_id,
            json.dumps(
                {
                    "sample_text": "你好。",
                    "provider_hints": {"elevenlabs_voice_id": "voice_abc123"},
                }
            ),
        )

        resp = client.post(
            f"/api/sessions/{session_id}/voice-sample",
            json={"provider": "elevenlabs"},
        )
        # With a saved voice_id the guard is passed. The downstream ElevenLabs call will
        # fail because no real API key is configured, but it must NOT be the guard error.
        assert resp.status_code != 400
        body = resp.json()
        assert "专属音色" not in (body.get("detail") or body.get("error") or "")


def main() -> None:
    test_voice_sample_blocks_elevenlabs_without_voice_id()
    test_voice_sample_allows_edge_tts_without_voice_id()
    test_voice_sample_allows_elevenlabs_with_voice_id()
    print("voice sample endpoint guard tests passed")


if __name__ == "__main__":
    main()
