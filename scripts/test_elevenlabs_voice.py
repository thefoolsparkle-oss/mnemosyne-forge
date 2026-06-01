"""Run OC draft -> ElevenLabs Voice Design -> saved voice -> Chinese TTS.

Usage:
    python scripts/test_elevenlabs_voice.py 30b635b02db2

Requires ELEVENLABS_API_KEY in the environment or project .env file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.oc_voice_director import analyze_voice  # noqa: E402
from app.voice_providers.elevenlabs_provider import ElevenLabsProvider  # noqa: E402


def _safe_name(value: str | None) -> str:
    text = value or "character"
    for ch in '\\/:*?"<>|':
        text = text.replace(ch, "_")
    return text[:40]


def _long_sample(profile: dict) -> str:
    variants = [str(v).strip() for v in (profile.get("sample_variants") or []) if str(v).strip()]
    lines = []
    if profile.get("sample_text"):
        lines.append(str(profile["sample_text"]).strip())
    lines.extend(variants)
    if not lines:
        lines = [
            "别靠近我。那不是你该碰的东西。",
            "我没有在等谁，只是这里比较安静。",
            "如果你一定要留下，就别问我从前的事。",
        ]
    return " ".join(lines[:4])


async def run(session_id: str, text: str | None = None, select_preview: int = 1, redesign: bool = False) -> dict:
    db.init_db()
    session = db.get_session(session_id)
    if not session:
        raise SystemExit(f"Session not found: {session_id}")

    draft = session["draft"]
    profile = db.get_voice_profile(session_id) or await analyze_voice(draft)
    profile["character_name"] = draft.name
    profile.setdefault("provider_hints", {})
    profile["provider_hints"]["provider"] = "elevenlabs"
    profile["provider_hints"]["elevenlabs_selected_preview_index"] = select_preview
    if redesign:
        profile["provider_hints"]["elevenlabs_force_design"] = True

    sample_text = text or _long_sample(profile)
    output_dir = ROOT / "exports" / "voices"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session_id}_{_safe_name(draft.name)}_elevenlabs.mp3"

    provider = ElevenLabsProvider()
    audio_path = await provider.synthesize(sample_text, profile, str(output_path))
    db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))
    db.insert_voice_generation(
        session_id,
        "elevenlabs",
        sample_text,
        json.dumps(profile, ensure_ascii=False),
        audio_path,
    )

    hints = profile.get("provider_hints", {})
    return {
        "session_id": session_id,
        "character": draft.name,
        "sample_text": sample_text,
        "audio_path": audio_path,
        "voice_id": hints.get("elevenlabs_voice_id"),
        "generated_voice_id": hints.get("elevenlabs_generated_voice_id"),
        "selected_preview_index": hints.get("elevenlabs_selected_preview_index"),
        "voice_description": hints.get("elevenlabs_voice_description"),
        "preview_paths": hints.get("elevenlabs_preview_paths", []),
        "previews": hints.get("elevenlabs_previews", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id", help="Forge session id, e.g. 30b635b02db2")
    parser.add_argument("--text", help="Override the generated Chinese sample")
    parser.add_argument("--select-preview", type=int, default=1, choices=[1, 2, 3], help="Which ElevenLabs preview to save")
    parser.add_argument("--redesign", action="store_true", help="Generate fresh previews even if a voice_id already exists")
    args = parser.parse_args()
    report = asyncio.run(run(args.session_id, args.text, args.select_preview, args.redesign))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
