# Mnemosyne Forge — Unified Check Command
# Usage: py -m scripts.check
# Or:    python scripts/check.py

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
    ok &= run("node --check web/app.js", "JS Syntax")
    ok &= run(f"{sys.executable} -m compileall app scripts", "Python Compile")
    ok &= run(f"{sys.executable} scripts/test_selected_assets_export.py", "Smoke Test")
    ok &= run(f"{sys.executable} scripts/index_legacy_exports.py", "Legacy Index")
    print(f"\n=== {'ALL OK' if ok else 'SOME FAILED'} ===")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
