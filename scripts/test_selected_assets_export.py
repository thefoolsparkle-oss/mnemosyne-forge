"""Smoke test for selected asset export/bridge payloads.

This does not call external LLM, image, voice, or bridge APIs.
"""

from __future__ import annotations

import asyncio
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")

    def safe_load(_: object) -> dict:
        return {
            "app": {
                "database_path": "data/forge.db",
                "export_dir": "exports",
            },
        }

    yaml_stub.safe_load = safe_load  # type: ignore[attr-defined]
    sys.modules["yaml"] = yaml_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    sys.modules["dotenv"] = dotenv_stub

if "httpx" not in sys.modules:
    httpx_stub = types.ModuleType("httpx")

    class AsyncClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "AsyncClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    httpx_stub.AsyncClient = AsyncClient  # type: ignore[attr-defined]
    sys.modules["httpx"] = httpx_stub

from app import db, mnemosyne_bridge, oc_export
from app.config import get_project_root
from app.oc_models import OCDraft


def _build_draft(name: str) -> OCDraft:
    return OCDraft(
        name=name,
        core_concept="A test character for selected asset export.",
        personality=["calm"],
        appearance="silver hair, blue eyes, dark coat",
        background="Created by a smoke test.",
        scenario="Testing export.",
        first_message="Hello.",
        example_dialogue=f"{name}: Hello.\nUser: Hi.",
        completion_score=1.0,
    )


async def _run_export(session_id: str) -> dict:
    async def fake_missing_fields(_: OCDraft) -> dict:
        return {}

    oc_export._generate_missing_fields = fake_missing_fields  # type: ignore[attr-defined]
    return await oc_export.export_card_v2(session_id)


async def test_basic_selected_assets() -> None:
    db.init_db()
    session_id = f"smoke_assets_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc).isoformat()
    draft = _build_draft("Smoke Test Character")
    db.create_session(session_id, 0, "Selected asset smoke test", draft, now, now)

    export_path: Path | None = None
    md_path: Path | None = None
    try:
        image_candidate_id = db.insert_asset(
            session_id,
            "image_candidate",
            "stability",
            "exports/images/smoke_candidate.png",
            {"prompt": "candidate prompt"},
        )
        db.insert_asset(
            session_id,
            "image_locked",
            "stability",
            "exports/images/smoke_locked.png",
            {"locked_prompt": "locked prompt", "source_candidate_id": image_candidate_id},
            selected=True,
        )
        db.insert_asset(
            session_id,
            "voice_identity",
            "elevenlabs",
            "voice_smoke_id",
            {"voice_name": "Smoke Voice"},
            selected=True,
        )
        db.insert_asset(
            session_id,
            "voice_sample",
            "elevenlabs",
            "exports/voices/smoke_sample.mp3",
            {"audio_url": "/exports/voices/smoke_sample.mp3"},
            selected=True,
        )

        result = await _run_export(session_id)
        assert result["ok"], result
        export_path = Path(result["file_path"])
        md_path = get_project_root() / "exports" / f"{session_id}_角色卡.md"

        selected = result["card"]["data"]["extensions"]["mnemosyne_forge"]["selected_assets"]
        assert selected["image"]["path"].endswith("smoke_locked.png")
        assert selected["voice_identity"]["path"] == "voice_smoke_id"
        assert selected["voice_audio"]["path"].endswith("smoke_sample.mp3")

        bridge_assets = mnemosyne_bridge._selected_assets_payload(session_id)
        assert bridge_assets["image_path"].endswith("smoke_locked.png")
        assert bridge_assets["voice_id"] == "voice_smoke_id"
        assert bridge_assets["voice_path"].endswith("smoke_sample.mp3")
        print("basic selected assets smoke test passed")
    finally:
        db.delete_session(session_id)
        if export_path and export_path.exists():
            export_path.unlink()
        if md_path and md_path.exists():
            md_path.unlink()


async def test_full_selected_assets_snapshot() -> None:
    """Snapshot the full selected_assets payload with every asset type present.

    Ensures the export/bridge payload picks the *selected* asset for each category
    and preserves metadata such as style, voice_name and audio_url.
    """
    db.init_db()
    session_id = f"full_assets_{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc).isoformat()
    draft = _build_draft("Full Snapshot Character")
    db.create_session(session_id, 0, "Full asset snapshot test", draft, now, now)

    export_path: Path | None = None
    md_path: Path | None = None
    try:
        # Image candidates + locked visual canon
        candidate_a = db.insert_asset(
            session_id,
            "image_candidate",
            "stability",
            "exports/images/full_candidate_a.png",
            {"style": "anime portrait", "prompt": "candidate a prompt"},
        )
        db.insert_asset(
            session_id,
            "image_candidate",
            "stability",
            "exports/images/full_candidate_b.png",
            {"style": "game concept", "prompt": "candidate b prompt"},
        )
        locked_id = db.insert_asset(
            session_id,
            "image_locked",
            "stability",
            "exports/images/full_locked.png",
            {
                "locked_prompt": "locked prompt",
                "selected_style": "anime character key visual",
                "source_candidate_id": candidate_a,
            },
            selected=True,
        )

        # Voice previews + identity + sample + performance candidate
        db.insert_asset(
            session_id,
            "voice_preview",
            "elevenlabs",
            "exports/voices/full_preview_1.mp3",
            {"index": 1, "generated_voice_id": "prev_1"},
        )
        db.insert_asset(
            session_id,
            "voice_preview",
            "elevenlabs",
            "exports/voices/full_preview_2.mp3",
            {"index": 2, "generated_voice_id": "prev_2"},
        )
        db.insert_asset(
            session_id,
            "voice_identity",
            "elevenlabs",
            "full_voice_id",
            {"voice_name": "Full Snapshot Voice", "selected_preview_index": 2},
            selected=True,
        )
        db.insert_asset(
            session_id,
            "voice_performance_candidate",
            "elevenlabs",
            "exports/voices/full_perf_candidate.mp3",
            {"label": "表现力", "sample_text": "你好。"},
        )
        db.insert_asset(
            session_id,
            "voice_sample",
            "elevenlabs",
            "exports/voices/full_sample.mp3",
            {"audio_url": "/exports/voices/full_sample.mp3", "sample_text": "你好。"},
            selected=True,
        )

        result = await _run_export(session_id)
        assert result["ok"], result
        export_path = Path(result["file_path"])
        md_path = get_project_root() / "exports" / f"{session_id}_角色卡.md"

        selected = result["card"]["data"]["extensions"]["mnemosyne_forge"]["selected_assets"]

        # Image must be the locked canon, not a candidate.
        assert selected["image"]["path"].endswith("full_locked.png")
        assert selected["image"]["metadata"]["selected_style"] == "anime character key visual"
        assert selected["image"]["metadata"]["source_candidate_id"] == candidate_a

        # Voice identity must be the selected one.
        assert selected["voice_identity"]["path"] == "full_voice_id"
        assert selected["voice_identity"]["metadata"]["voice_name"] == "Full Snapshot Voice"

        # Voice audio must prefer selected voice_sample over preview/performance candidate.
        assert selected["voice_audio"]["path"].endswith("full_sample.mp3")
        assert selected["voice_audio"]["metadata"]["audio_url"] == "/exports/voices/full_sample.mp3"

        # Bridge payload mirrors the selected assets.
        bridge = mnemosyne_bridge._selected_assets_payload(session_id)
        assert bridge["image_path"].endswith("full_locked.png")
        assert bridge["voice_id"] == "full_voice_id"
        assert bridge["voice_path"].endswith("full_sample.mp3")

        # Snapshot: ensure the extension shape is stable.
        assert set(selected.keys()) == {"image", "voice_identity", "voice_audio", "by_type"}
        by_type = selected["by_type"]
        assert by_type["image_locked"]["path"].endswith("full_locked.png")
        assert by_type["voice_identity"]["path"] == "full_voice_id"
        assert by_type["voice_sample"]["path"].endswith("full_sample.mp3")
        assert by_type["voice_preview"]["path"].endswith("full_preview_2.mp3")
        assert by_type["voice_performance_candidate"]["path"].endswith("full_perf_candidate.mp3")
        print("full selected assets snapshot test passed")
    finally:
        db.delete_session(session_id)
        if export_path and export_path.exists():
            export_path.unlink()
        if md_path and md_path.exists():
            md_path.unlink()


async def main() -> None:
    await test_basic_selected_assets()
    await test_full_selected_assets_snapshot()


if __name__ == "__main__":
    asyncio.run(main())
