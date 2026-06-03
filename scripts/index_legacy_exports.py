"""Index legacy files under exports/ into the assets table.

Default mode is dry-run. Use --apply to write inferred assets.
Only files with an inferable session id are indexed; ambiguous files are reported.
"""

from __future__ import annotations

import argparse
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda _stream: {"app": {"database_path": "data/forge.db", "export_dir": "exports"}}  # type: ignore[attr-defined]
    sys.modules["yaml"] = yaml_stub

if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    sys.modules["dotenv"] = dotenv_stub

from app import db  # noqa: E402

SESSION_RE = re.compile(r"^[0-9a-f]{12}$")
VOICE_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def infer_session_id(path: Path, known_sessions: set[str]) -> str | None:
    stem_token = path.stem.split("_", 1)[0]
    if stem_token in known_sessions:
        return stem_token
    for parent in path.parents:
        if parent.name in known_sessions:
            return parent.name
        parent_token = parent.name.split("_", 1)[0]
        if parent_token in known_sessions:
            return parent_token
    if SESSION_RE.match(stem_token):
        return stem_token
    return None


def provider_from_name(path: Path) -> str:
    name = path.name.lower()
    if "elevenlabs" in name:
        return "elevenlabs"
    if "fish" in name:
        return "fish_audio"
    if "edge" in name:
        return "edge_tts"
    if "stability" in name:
        return "stability"
    return "legacy"


def main() -> None:
    parser = argparse.ArgumentParser(description="Index legacy exports into assets.")
    parser.add_argument("--apply", action="store_true", help="Write inferred assets to the database.")
    args = parser.parse_args()

    db.init_db()
    sessions = db.list_sessions(user_id=None)
    known_sessions = {s["id"] for s in sessions}
    existing_paths = {
        str(Path(asset["path"]).resolve(strict=False)).lower()
        for session_id in known_sessions
        for asset in db.list_assets(session_id)
        if asset.get("path")
    }

    exports_dir = ROOT / "exports"
    indexed: list[dict] = []
    skipped: list[dict] = []
    inserted = 0

    for path in exports_dir.rglob("*"):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        suffix = path.suffix.lower()
        if suffix not in VOICE_EXTS | IMAGE_EXTS:
            continue
        resolved_key = str(path.resolve(strict=False)).lower()
        if resolved_key in existing_paths:
            skipped.append({"path": str(path), "reason": "already_indexed"})
            continue

        session_id = infer_session_id(path, known_sessions)
        if not session_id or session_id not in known_sessions:
            skipped.append({"path": str(path), "reason": "unknown_session"})
            continue

        if suffix in VOICE_EXTS:
            asset_type = "voice_sample"
        elif suffix in IMAGE_EXTS:
            asset_type = "image_candidate"
        else:
            skipped.append({"path": str(path), "reason": "unsupported_type"})
            continue

        record = {
            "session_id": session_id,
            "asset_type": asset_type,
            "provider": provider_from_name(path),
            "path": str(path),
            "metadata": {
                "source": "legacy_exports_index",
                "file_name": path.name,
                "size_bytes": path.stat().st_size,
            },
        }
        indexed.append(record)
        if args.apply:
            db.insert_asset(
                record["session_id"],
                record["asset_type"],
                record["provider"],
                record["path"],
                record["metadata"],
            )
            inserted += 1

    print(f"known_sessions={len(known_sessions)}")
    print(f"would_index={len(indexed)}")
    print(f"inserted={inserted}")
    print(f"skipped={len(skipped)}")
    for item in indexed[:30]:
        print(f"INDEX {item['session_id']} {item['asset_type']} {item['provider']} {item['path']}")
    for item in skipped[:30]:
        print(f"SKIP {item['reason']} {item['path']}")


if __name__ == "__main__":
    main()
