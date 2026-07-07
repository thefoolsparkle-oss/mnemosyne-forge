"""Custom / "other" image generation provider.

Accepts per-request overrides for base_url, model, api_key and the HTTP payload
shape. This lets users plug in any OpenAI-compatible image endpoint without
needing a dedicated provider implementation.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from ..config import get_project_root
from ..oc_models import OCDraft
from .base import ImageProvider


class CustomProvider(ImageProvider):
    name = "custom"

    async def generate(
        self,
        draft: OCDraft,
        style: str,
        prompt: str,
        negative_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        base_url = (kwargs.get("base_url") or "").rstrip("/")
        api_key = kwargs.get("api_key", "")
        model = kwargs.get("model", "")

        if not base_url:
            return {
                "ok": False,
                "error": "自定义模型需要填写 base_url",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }
        if not api_key:
            return {
                "ok": False,
                "error": "自定义模型需要填写 API Key",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }
        if not model:
            return {
                "ok": False,
                "error": "自定义模型需要填写模型名称",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }

        # Merge negative prompt into the prompt for generic endpoints.
        final_prompt = prompt
        if negative_prompt:
            final_prompt += f"\nAvoid: {negative_prompt}."

        payload = {
            "model": model,
            "prompt": final_prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        if kwargs.get("size"):
            payload["size"] = kwargs["size"]
        if kwargs.get("quality"):
            payload["quality"] = kwargs["quality"]

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
                    "error": f"自定义模型鉴权失败 ({resp.status_code}): {resp.text[:300]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }
            if resp.status_code >= 400:
                return {
                    "ok": False,
                    "error": f"自定义模型返回 {resp.status_code}: {resp.text[:500]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": None,
                }

            data = resp.json()
            images = data.get("data", [])
            if not images or not images[0].get("b64_json"):
                # Some custom endpoints return url instead of b64_json.
                if images and images[0].get("url"):
                    url = images[0]["url"]
                    async with httpx.AsyncClient(timeout=60.0) as download_client:
                        img_resp = await download_client.get(url)
                    if img_resp.status_code != 200:
                        return {
                            "ok": False,
                            "error": f"无法下载自定义模型图片: {img_resp.status_code}",
                            "prompt": prompt,
                            "negative_prompt": negative_prompt,
                            "seed": None,
                        }
                    image_data = img_resp.content
                else:
                    return {
                        "ok": False,
                        "error": "自定义模型未返回图片",
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "seed": None,
                    }
            else:
                image_data = base64.b64decode(images[0]["b64_json"])

            output_dir = get_project_root() / "exports" / "images"
            output_dir.mkdir(parents=True, exist_ok=True)

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
                "error": f"自定义模型生图失败: {e}",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": None,
            }
