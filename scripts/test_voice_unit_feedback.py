"""Tests for per-unit voice feedback loop: regenerate + favorite.

These tests do not call external ElevenLabs APIs. They mock the provider's
`text_to_speech` method and verify that the endpoints update the voice profile
and assets as expected.
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
from app.voice_providers import elevenlabs_provider

_test_db_path = app_config.get_project_root() / "data" / "test_forge_voice_unit.db"
_test_auth_path = app_config.get_project_root() / "data" / "test_auth_voice_unit.db"

app_config._config_cache = {
    "app": {
        "database_path": "data/test_forge_voice_unit.db",
        "export_dir": "exports",
    },
    "auth": {"shared_db_path": str(_test_auth_path)},
    "voice": {"provider": "elevenlabs", "output_dir": "exports/voices"},
}
auth._auth_db_cache = None
_test_db_path.unlink(missing_ok=True)
_test_auth_path.unlink(missing_ok=True)

from app import server  # noqa: E402


def _admin_auth(client: TestClient) -> None:
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


def _create_session() -> str:
    session_id = f"voice_unit_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    draft = OCDraft(name="Voice Unit Test", core_concept="test character")
    db.create_session(session_id, 0, "voice unit test", draft, now, now)
    return session_id


def _save_profile(session_id: str) -> None:
    profile = {
        "sample_text": "你好。再见。",
        "provider_hints": {
            "elevenlabs_voice_id": "voice_test_123",
            "performance_units": [
                {
                    "unit_index": 0,
                    "clean_text": "你好。",
                    "emotion": "calm",
                    "speed": "normal",
                    "volume": "normal",
                    "distance": "casual",
                },
                {
                    "unit_index": 1,
                    "clean_text": "再见。",
                    "emotion": "sad",
                    "speed": "slow",
                    "volume": "soft",
                    "distance": "distant",
                },
            ],
        },
    }
    db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))


def test_voice_unit_regenerate() -> None:
    original_tts = elevenlabs_provider.ElevenLabsProvider.text_to_speech

    async def fake_tts(self, text, voice_id, profile, output_path, **kwargs):
        Path(output_path).write_bytes(b"fake audio")
        return output_path

    elevenlabs_provider.ElevenLabsProvider.text_to_speech = fake_tts
    try:
        with TestClient(server.app) as client:
            _admin_auth(client)
            session_id = _create_session()
            _save_profile(session_id)

            resp = client.post(
                f"/api/sessions/{session_id}/voice-unit-regenerate",
                json={"unit_index": 1, "emotion": "cold", "speed": "fast"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["ok"] is True, body
            assert body["unit_index"] == 1
            assert body["clean_text"] == "再见。"
            assert body["unit"]["emotion"] == "cold"
            assert body["unit"]["speed"] == "fast"
            assert body["audio_path"].endswith("_unit1_regen.mp3")
    finally:
        elevenlabs_provider.ElevenLabsProvider.text_to_speech = original_tts


def test_voice_unit_favorite() -> None:
    with TestClient(server.app) as client:
        _admin_auth(client)
        session_id = _create_session()
        _save_profile(session_id)

        resp = client.post(
            f"/api/sessions/{session_id}/voice-unit-favorite",
            json={"unit_index": 0, "note": "natural pause"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["favorites_count"] == 1

        profile = db.get_voice_profile(session_id)
        assert profile is not None
        favorites = profile.get("unit_favorites", [])
        assert len(favorites) == 1
        assert favorites[0]["unit_index"] == 0
        assert favorites[0]["unit"]["clean_text"] == "你好。"
        assert favorites[0]["note"] == "natural pause"


def test_voice_unit_regenerate_requires_voice_id() -> None:
    with TestClient(server.app) as client:
        _admin_auth(client)
        session_id = _create_session()
        db.save_voice_profile(
            session_id,
            json.dumps({
                "sample_text": "你好。",
                "provider_hints": {
                    "performance_units": [
                        {"unit_index": 0, "clean_text": "你好。", "emotion": "calm", "speed": "normal", "volume": "normal"}
                    ]
                },
            }),
        )
        resp = client.post(
            f"/api/sessions/{session_id}/voice-unit-regenerate",
            json={"unit_index": 0},
        )
        assert resp.status_code == 400
        assert "专属音色" in resp.json()["detail"]


def main() -> None:
    test_voice_unit_regenerate()
    test_voice_unit_favorite()
    test_voice_unit_regenerate_requires_voice_id()
    print("voice unit feedback tests passed")


if __name__ == "__main__":
    main()
