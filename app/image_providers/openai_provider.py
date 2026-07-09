"""OpenAI DALL-E image generation provider.

Supports DALL-E 3 and future DALL-E variants through the OpenAI images API.
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


class OpenAIProvider(ImageProvider):
    name = "openai"

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
        provider_cfg = img_cfg.get("providers", {}).get("openai", {})
        api_key = read_env(provider_cfg.get("api_key_env", "OPENAI_API_KEY"))

        if not api_key:
            return {
                "ok": False,
                "error": "OpenAI API Key 未配置，请设置 OPENAI_API_KEY 环境变量",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }

        model = provider_cfg.get("model", "dall-e-3")
        size = provider_cfg.get("size", "1024x1024")
        quality = provider_cfg.get("quality", "standard")
        base_url = provider_cfg.get("base_url", "https://api.openai.com/v1")

        # DALL-E does not support negative prompts natively; merge into prompt if given.
        final_prompt = prompt
        if negative_prompt:
            final_prompt += f"\nAvoid: {negative_prompt}."

        payload = {
            "model": model,
            "prompt": final_prompt,
            "size": size,
            "quality": quality,
            "n": 1,
            "response_format": "b64_json",
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/images/generations",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

            if resp.status_code in (401, 403):
                return {
                    "ok": False,
                    "error": f"OpenAI auth/permission failed ({resp.status_code}): {resp.text[:300]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"OpenAI API returned {resp.status_code}: {resp.text[:500]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }

            data = resp.json()
            images = data.get("data", [])
            if not images or not images[0].get("b64_json"):
                return {
                    "ok": False,
                    "error": "OpenAI API 未返回图片",
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
                "error": f"OpenAI 生图失败: {e}",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }
