"""Run the full OC -> voice casting -> Fish Audio sample pipeline locally.

Usage:
    python scripts/test_voice_cast.py 30b635b02db2

This script intentionally runs on the user's machine. It reads the local OC
draft, calls the configured LLM to build a VoiceProfile, casts a Fish reference
voice, then generates an mp3 under exports/voices/.
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
from app.oc_voice_casting import cast_voice  # noqa: E402
from app.oc_voice_director import analyze_voice  # noqa: E402
from app.voice_providers.fish_audio_provider import FishAudioProvider  # noqa: E402


def _safe_name(value: str | None) -> str:
    text = value or "character"
    for ch in '\\/:*?"<>|':
        text = text.replace(ch, "_")
    return text[:40]


async def run(session_id: str, text: str | None = None) -> dict:
    db.init_db()
    session = db.get_session(session_id)
    if not session:
        raise SystemExit(f"Session not found: {session_id}")

    draft = session["draft"]
    profile = await analyze_voice(draft)
    cast = await cast_voice(draft, profile, limit=8)
    recommendation = cast.get("recommendation") or {}

    profile.setdefault("provider_hints", {})
    if recommendation.get("reference_id"):
        profile["provider_hints"]["fish_reference_id"] = recommendation["reference_id"]
        profile["provider_hints"]["voice_casting_source"] = recommendation.get("source")

    sample_text = text or profile.get("sample_text")
    if not sample_text:
        sample_text = "别靠近我。你看见的，不过是我留下来的壳。"

    output_dir = ROOT / "exports" / "voices"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{session_id}_{_safe_name(draft.name)}_voice_cast_fish.mp3"
    audio_path = await FishAudioProvider().synthesize(sample_text, profile, str(output_path))

    report = {
        "session_id": session_id,
        "character": draft.name,
        "core_concept": draft.core_concept,
        "sample_text": sample_text,
        "audio_path": audio_path,
        "reference_id": profile.get("provider_hints", {}).get("fish_reference_id"),
        "casting_recommendation": recommendation,
        "fish_tts_directive": profile.get("fish_tts_directive"),
        "sample_variants": profile.get("sample_variants", []),
    }
    db.save_voice_profile(session_id, json.dumps(profile, ensure_ascii=False))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id", help="Forge session id, e.g. 30b635b02db2")
    parser.add_argument("--text", help="Override the generated sample line")
    args = parser.parse_args()

    report = asyncio.run(run(args.session_id, args.text))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
