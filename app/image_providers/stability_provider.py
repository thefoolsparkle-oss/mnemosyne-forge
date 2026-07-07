"""Stability AI image generation provider."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import httpx

from ..config import get_config, get_project_root
from ..env_utils import read_env
from ..oc_models import OCDraft
from .base import ImageProvider


class StabilityProvider(ImageProvider):
    name = "stability"

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
        provider_cfg = img_cfg.get("providers", {}).get("stability", {})
        api_key = read_env(provider_cfg.get("api_key_env", "STABILITY_API_KEY"))
        style = _normalize_character_style(style)

        if not api_key:
            return {
                "ok": False,
                "error": "Stability API Key 未配置，请设置 STABILITY_API_KEY 环境变量",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }

        model = provider_cfg.get("model", img_cfg.get("model", "sd3.5-large"))
        aspect_ratio = provider_cfg.get("aspect_ratio", img_cfg.get("aspect_ratio", "1:1"))

        if str(model).startswith("sd3"):
            url = "https://api.stability.ai/v2beta/stable-image/generate/sd3"
        else:
            url = "https://api.stability.ai/v2beta/stable-image/generate/core"

        fields = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "output_format": "png",
            "aspect_ratio": aspect_ratio,
        }
        if str(model).startswith("sd3"):
            fields["model"] = model

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Accept": "application/json",
                    },
                    files={k: (None, v) for k, v in fields.items()},
                )

            if resp.status_code in (401, 403):
                return {
                    "ok": False,
                    "error": f"Stability API auth/permission failed ({resp.status_code}): {resp.text[:300]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }
            if resp.status_code != 200:
                return {
                    "ok": False,
                    "error": f"Stability API returned {resp.status_code}: {resp.text[:500]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }

            data = resp.json()
            image_b64 = data.get("image", "")
            if not image_b64:
                return {
                    "ok": False,
                    "error": "API 未返回图片",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }

            output_dir = get_project_root() / "exports" / "images"
            output_dir.mkdir(parents=True, exist_ok=True)

            image_data = base64.b64decode(image_b64)
            seed = data.get("seed", 0)
            filename = f"{draft.name or 'character'}_{seed}.png"
            image_path = output_dir / filename
            image_path.write_bytes(image_data)

            return {
                "ok": True,
                "image_path": str(image_path),
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": seed,
                "finish_reason": data.get("finish_reason"),
            }

        except Exception as e:
            return {
                "ok": False,
                "error": f"生图失败: {e}",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }


def _normalize_character_style(style: str) -> str:
    """Keep first-pass OC candidates in useful character-portrait styles."""
    raw = (style or "").strip()
    lowered = raw.lower()
    if "flat" in lowered or "illustration" in lowered:
        return "high-detail game character concept art, polished anime rendering, expressive eyes"
    if lowered in {"anime", "anime portrait"}:
        return "premium anime character key visual, detailed face, layered painterly lighting"
    if "cinematic" in lowered:
        return "anime character portrait, cinematic rim light, dramatic library atmosphere"
    return raw or "premium anime character key visual, detailed face, layered painterly lighting"
