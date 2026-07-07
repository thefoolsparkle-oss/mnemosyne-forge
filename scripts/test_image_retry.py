"""Tests for /image-candidates retry behaviour.

Retry mode is triggered when the frontend sends retry_prompt (+ optional
retry_negative_prompt). In that mode the endpoint must:

1. Skip Visual Identity analysis and Prompt Director.
2. Generate exactly one candidate instead of three.

The test uses FastAPI TestClient with mocked image generation, critique and
prompt-building helpers so no external APIs are called.
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

_test_db_path = app_config.get_project_root() / "data" / "test_forge_image_retry.db"
_test_auth_path = app_config.get_project_root() / "data" / "test_auth_image_retry.db"

app_config._config_cache = {
    "app": {
        "database_path": "data/test_forge_image_retry.db",
        "export_dir": "exports",
    },
    "auth": {"shared_db_path": str(_test_auth_path)},
    "voice": {"provider": "elevenlabs"},
}
auth._auth_db_cache = None
_test_db_path.unlink(missing_ok=True)
_test_auth_path.unlink(missing_ok=True)

from app import oc_image_gen, oc_image_critic, oc_visual_identity, oc_image_prompt_director, server  # noqa: E402


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
    session_id = f"img_retry_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    draft = OCDraft(
        name="Image Retry Test",
        core_concept="a test character for image retry",
        appearance="silver hair",
    )
    db.create_session(session_id, 0, "image retry test", draft, now, now)
    return session_id


def _mock_generate_character_image():
    call_count = {"n": 0}

    async def _fake_generate(draft, style, prompt=None, negative_prompt=None):
        call_count["n"] += 1
        return {
            "ok": True,
            "image_path": f"exports/images/retry_{call_count['n']}_{style.replace(' ', '_')}.png",
            "prompt": prompt or "mock prompt",
            "negative_prompt": negative_prompt or "mock negative",
            "seed": 42,
        }

    return _fake_generate, call_count


def test_retry_skips_visual_identity_and_director() -> None:
    identity_called = {"n": 0}
    director_called = {"n": 0}

    async def fake_identity(draft):
        identity_called["n"] += 1
        raise AssertionError("Visual Identity should not be called in retry mode")

    async def fake_director(draft, visual):
        director_called["n"] += 1
        raise AssertionError("Prompt Director should not be called in retry mode")

    fake_generate, call_count = _mock_generate_character_image()

    original_identity = oc_visual_identity.analyze_visual_identity
    original_director = oc_image_prompt_director.direct_image_prompt
    original_generate = oc_image_gen.generate_character_image

    oc_visual_identity.analyze_visual_identity = fake_identity
    oc_image_prompt_director.direct_image_prompt = fake_director
    oc_image_gen.generate_character_image = fake_generate

    try:
        with TestClient(server.app) as client:
            _admin_auth(client)
            session_id = _create_session()
            resp = client.post(
                f"/api/sessions/{session_id}/image-candidates",
                json={
                    "retry_style": "anime portrait cinematic rim light",
                    "retry_prompt": "retry prompt text",
                    "retry_negative_prompt": "retry negative text",
                },
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("ok") is True, body
            assert identity_called["n"] == 0, "Visual Identity was called during retry"
            assert director_called["n"] == 0, "Prompt Director was called during retry"
            assert call_count["n"] == 1, f"expected 1 candidate, got {call_count['n']}"
            candidates = body.get("candidates", [])
            assert len(candidates) == 1, f"expected 1 candidate in response, got {len(candidates)}"
            assert candidates[0]["style"] == "anime portrait cinematic rim light"
            assert candidates[0]["prompt"] == "retry prompt text"
            assert candidates[0]["negative_prompt"] == "retry negative text"
    finally:
        oc_visual_identity.analyze_visual_identity = original_identity
        oc_image_prompt_director.direct_image_prompt = original_director
        oc_image_gen.generate_character_image = original_generate


def test_retry_generates_single_candidate_even_with_style_only() -> None:
    """If only retry_style is provided without retry_prompt, the endpoint falls back
    to running Visual Identity + Director and then filters to a single variation.
    This test verifies the single-candidate contract for that path.
    """
    fake_generate, call_count = _mock_generate_character_image()
    original_generate = oc_image_gen.generate_character_image

    async def fake_identity(draft):
        return {"hairstyle": "silver", "outfit": "coat"}

    async def fake_director(draft, visual):
        return {
            "positive_prompt": "directed prompt",
            "variations": [
                {"style": "anime portrait", "positive_prompt": "v1"},
                {"style": "anime portrait cinematic rim light", "positive_prompt": "v2"},
                {"style": "game character concept art", "positive_prompt": "v3"},
            ],
        }

    original_identity = oc_visual_identity.analyze_visual_identity
    original_director = oc_image_prompt_director.direct_image_prompt
    oc_visual_identity.analyze_visual_identity = fake_identity
    oc_image_prompt_director.direct_image_prompt = fake_director
    oc_image_gen.generate_character_image = fake_generate

    try:
        with TestClient(server.app) as client:
            _admin_auth(client)
            session_id = _create_session()
            resp = client.post(
                f"/api/sessions/{session_id}/image-candidates",
                json={"retry_style": "anime portrait cinematic rim light"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("ok") is True, body
            assert call_count["n"] == 1, f"expected 1 candidate, got {call_count['n']}"
            candidates = body.get("candidates", [])
            assert len(candidates) == 1, f"expected 1 candidate in response, got {len(candidates)}"
            assert candidates[0]["style"] == "anime portrait cinematic rim light"
    finally:
        oc_visual_identity.analyze_visual_identity = original_identity
        oc_image_prompt_director.direct_image_prompt = original_director
        oc_image_gen.generate_character_image = original_generate


def test_normal_mode_generates_three_candidates() -> None:
    """Without retry params the endpoint should still generate up to three candidates."""
    fake_generate, call_count = _mock_generate_character_image()
    original_generate = oc_image_gen.generate_character_image

    async def fake_identity(draft):
        return {"hairstyle": "silver", "outfit": "coat"}

    async def fake_director(draft, visual):
        return {
            "positive_prompt": "directed prompt",
            "variations": [
                {"style": "anime character key visual", "positive_prompt": "v1"},
                {"style": "anime portrait cinematic rim light", "positive_prompt": "v2"},
                {"style": "game character concept art", "positive_prompt": "v3"},
            ],
        }

    original_identity = oc_visual_identity.analyze_visual_identity
    original_director = oc_image_prompt_director.direct_image_prompt
    oc_visual_identity.analyze_visual_identity = fake_identity
    oc_image_prompt_director.direct_image_prompt = fake_director
    oc_image_gen.generate_character_image = fake_generate

    try:
        with TestClient(server.app) as client:
            _admin_auth(client)
            session_id = _create_session()
            resp = client.post(
                f"/api/sessions/{session_id}/image-candidates",
                json={},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body.get("ok") is True, body
            assert call_count["n"] == 3, f"expected 3 candidates, got {call_count['n']}"
            assert len(body.get("candidates", [])) == 3
    finally:
        oc_visual_identity.analyze_visual_identity = original_identity
        oc_image_prompt_director.direct_image_prompt = original_director
        oc_image_gen.generate_character_image = original_generate


def main() -> None:
    test_retry_skips_visual_identity_and_director()
    test_retry_generates_single_candidate_even_with_style_only()
    test_normal_mode_generates_three_candidates()
    print("image retry tests passed")


if __name__ == "__main__":
    main()
