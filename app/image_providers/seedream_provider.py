"""Seedream image generation provider (Volcano Ark / ByteDance).

Seedream is exposed through the Volcano Ark platform and uses an
OpenAI-compatible images API. This provider presets the Ark base URL and
common Seedream model IDs while still allowing the user to override them.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from ..config import get_config, get_project_root
from ..env_utils import read_env
from ..oc_models import OCDraft
from .base import ImageProvider

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# Common Seedream model IDs on Volcano Ark. Users can override in config or per-request.
DEFAULT_MODELS = [
    "seedream-3-0-t2i-250722",
]


class SeedreamProvider(ImageProvider):
    name = "seedream"

    async def generate(
        self,
        draft: OCDraft,
        style: str,
        prompt: str,
        negative_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        cfg = get_config()
        img_cfg = cfg.get("image", {})
        provider_cfg = img_cfg.get("providers", {}).get("seedream", {})
        api_key = read_env(provider_cfg.get("api_key_env", "SEEDREAM_API_KEY"))

        if not api_key:
            return {
                "ok": False,
                "error": "Seedream API Key 未配置，请设置 SEEDREAM_API_KEY 环境变量",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }

        base_url = (kwargs.get("base_url") or provider_cfg.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        model = kwargs.get("model") or provider_cfg.get("model") or DEFAULT_MODELS[0]
        size = kwargs.get("size") or provider_cfg.get("size", "1024x1024")

        # Seedream does not support negative prompts natively; merge into prompt if given.
        final_prompt = prompt
        if negative_prompt:
            final_prompt += f"\n避免: {negative_prompt}"

        payload = {
            "model": model,
            "prompt": final_prompt,
            "size": size,
            "n": 1,
            "response_format": "b64_json",
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{base_url}/images/generations",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

            if resp.status_code in (401, 403):
                return {
                    "ok": False,
                    "error": f"Seedream 鉴权失败 ({resp.status_code}): {resp.text[:300]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"Seedream 返回 {resp.status_code}: {resp.text[:500]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }

            data = resp.json()
            images = data.get("data", [])
            if not images or not images[0].get("b64_json"):
                return {
                    "ok": False,
                    "error": "Seedream 未返回图片",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }

            output_dir = get_project_root() / "exports" / "images"
            output_dir.mkdir(parents=True, exist_ok=True)

            image_data = base64.b64decode(images[0]["b64_json"])
            seed = data.get("created", 0)
            filename = f"{draft.name or 'character'}_{seed}.png"
            image_path = output_dir / filename
            image_path.write_bytes(image_data)

            return {
                "ok": True,
                "image_path": str(image_path),
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": seed,
            }

        except Exception as e:
            return {
                "ok": False,
                "error": f"Seedream 生图失败: {e}",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }
