"""Pollinations.ai free image generation provider.

No API key is required. Used as the default fallback when the user has not
configured any paid image provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ..config import get_project_root
from ..oc_models import OCDraft
from .base import ImageProvider


class PollinationsProvider(ImageProvider):
    name = "pollinations"

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    async def generate(
        self,
        draft: OCDraft,
        style: str,
        prompt: str,
        negative_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Pollinations does not support negative prompts; merge if present.
        final_prompt = prompt
        if negative_prompt:
            final_prompt += f"\nAvoid: {negative_prompt}."

        seed = kwargs.get("seed") or 0
        width = kwargs.get("width") or 1024
        height = kwargs.get("height") or 1024
        encoded = quote(final_prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={width}&height={height}&seed={seed}&nologo=true"
        )

        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                resp = await client.get(url)

            if resp.status_code != 200:
                return {
                    "ok": False,
                    "error": f"Pollinations 返回 {resp.status_code}: {resp.text[:300]}",
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "seed": seed,
                }

            output_dir = get_project_root() / "exports" / "images"
            output_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{draft.name or 'character'}_{seed}.png"
            image_path = output_dir / filename
            image_path.write_bytes(resp.content)

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
                "error": f"Pollinations 生图失败: {e}",
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": seed,
            }
