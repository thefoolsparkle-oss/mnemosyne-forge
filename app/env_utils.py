"""Environment variable helpers."""

from __future__ import annotations

import os
import sys


def read_env(name: str) -> str:
    """Read an env var, including freshly-set Windows user/machine variables."""
    value = os.getenv(name, "")
    if value or sys.platform != "win32":
        return value
    try:
        import winreg

        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, "Environment") as key:
                    value, _ = winreg.QueryValueEx(key, name)
                    if value:
                        return str(value)
            except OSError:
                continue
    except Exception:
        return ""
    return ""
