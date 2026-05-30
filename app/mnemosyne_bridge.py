"""Bridge to Project Mnemosyne (忆界树) — v0.6

Allows importing a completed OC into 忆界树 as a chat-able persona.
Calls 忆界树's API at the configured bridge endpoint.
"""

from __future__ import annotations

import httpx
from typing import Any

from .config import get_config
from .oc_models import OCDraft


def _bridge_url() -> str:
    cfg = get_config()
    bridge = cfg.get("mnemosyne_bridge", {})
    enabled = bridge.get("enabled", False)
    if not enabled:
        raise RuntimeError("Mnemosyne bridge is not enabled in config.yaml")
    return bridge.get("base_url", "http://127.0.0.1:8001").rstrip("/")


async def check_bridge_health() -> dict:
    """Check if 忆界树 is reachable."""
    try:
        url = _bridge_url()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/health")
            return {"ok": resp.status_code == 200, "status": resp.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def import_to_mnemosyne(
    session_id: str,
    card_v2: dict,
    draft: OCDraft | None = None,
) -> dict:
    """Import a created OC as a persona into 忆界树.

    Sends the Character Card V2 JSON to 忆界树's persona import endpoint.
    """
    url = _bridge_url()

    payload: dict[str, Any] = {
        "source": "mnemosyne_forge",
        "card_v2": card_v2,
        "draft": draft.model_dump() if draft else {},
        "world_book": {},
        "assets": {"image_path": None, "voice_path": None},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/api/personas/import-from-oc",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code == 200:
                return {"ok": True, "data": resp.json()}
            return {"ok": False, "error": f"忆界树返回 {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"无法连接到忆界树（{url}）：{e}"}
