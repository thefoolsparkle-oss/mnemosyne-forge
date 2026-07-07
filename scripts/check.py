# Mnemosyne Forge - Unified Check Command
# Usage: py -m scripts.check
# Or:    python scripts/check.py
#
# Environment variables:
#   NODE_EXE - path to the Node.js executable (default: "node")

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, label):
    print(f"[{label}]", end=" ", flush=True)
    try:
        subprocess.run(cmd, cwd=str(ROOT), check=True, capture_output=True, text=True, shell=True)
        print("OK")
        return True
    except subprocess.CalledProcessError as e:
        print("FAIL")
        print("  " + (e.stderr or e.stdout or "no output")[:200])
        return False


def main():
    ok = True
    node_exe = os.environ.get("NODE_EXE", "node")
    ok &= run(f'{node_exe} --check web/app.js', "JS Syntax")
    ok &= run(f"{sys.executable} -m compileall app scripts", "Python Compile")
    ok &= run(f"{sys.executable} scripts/test_selected_assets_export.py", "Smoke Test")
    ok &= run(f"{sys.executable} scripts/test_voice_safety_and_performance.py", "Voice Safety")
    ok &= run(f"{sys.executable} scripts/test_voice_sample_endpoint.py", "Voice Endpoint Guard")
    ok &= run(f"{sys.executable} scripts/test_image_retry.py", "Image Retry")
    ok &= run(f"{sys.executable} scripts/test_voice_unit_feedback.py", "Voice Unit Feedback")
    ok &= run(f"{sys.executable} scripts/cleanup_orphan_exports.py --dry-run", "Export Cleanup")
    ok &= run(f"{sys.executable} scripts/index_legacy_exports.py", "Legacy Index")
    print(f"\n=== {'ALL OK' if ok else 'SOME FAILED'} ===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
