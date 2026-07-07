"""Cleanup orphan export files.

Scans exports/images and exports/voices and deletes files that are not referenced
by any row in the assets table. This prevents the export directories from growing
indefinitely as users regenerate images/voices.

Run manually:
    py scripts/cleanup_orphan_exports.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db
from app.config import get_project_root


ALLOWED_ROOTS = ("exports/images", "exports/voices")


def _referenced_paths() -> set[str]:
    """Return all asset paths currently stored in the database."""
    # list_assets requires a session_id, so we query directly for all paths.
    from app.db import _get_conn

    conn = _get_conn()
    try:
        rows = conn.execute("SELECT path FROM assets").fetchall()
        return {str(row["path"]) for row in rows}
    finally:
        conn.close()


def _is_under_allowed_root(path: Path) -> bool:
    project_root = get_project_root().resolve()
    resolved = path.resolve()
    return any(
        resolved == (project_root / root).resolve()
        or (project_root / root).resolve() in resolved.parents
        for root in ALLOWED_ROOTS
    )


def cleanup(dry_run: bool = False) -> dict:
    db.init_db()
    referenced = _referenced_paths()
    removed: list[str] = []
    skipped: list[str] = []
    project_root = get_project_root()

    for root_name in ALLOWED_ROOTS:
        root = project_root / root_name
        if not root.exists():
            continue
        for file_path in root.iterdir():
            if not file_path.is_file():
                continue
            if not _is_under_allowed_root(file_path):
                skipped.append(str(file_path))
                continue
            rel_path = file_path.relative_to(project_root).as_posix()
            if rel_path in referenced or str(file_path) in referenced:
                continue
            if dry_run:
                removed.append(str(file_path))
            else:
                try:
                    file_path.unlink()
                    removed.append(str(file_path))
                except OSError as exc:
                    skipped.append(f"{file_path}: {exc}")

    return {"removed": removed, "skipped": skipped, "dry_run": dry_run}


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove unreferenced export files.")
    parser.add_argument("--dry-run", action="store_true", help="List files without deleting.")
    args = parser.parse_args()

    result = cleanup(dry_run=args.dry_run)
    action = "would remove" if args.dry_run else "removed"
    print(f"{action}: {len(result['removed'])}")
    for p in result["removed"]:
        print("  -", p)
    if result["skipped"]:
        print(f"skipped: {len(result['skipped'])}")
        for p in result["skipped"]:
            print("  -", p)


if __name__ == "__main__":
    main()
