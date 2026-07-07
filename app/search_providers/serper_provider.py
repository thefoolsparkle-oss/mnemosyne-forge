"""Serper.dev search provider.

Serper exposes a Google Search API. It returns organic results with title,
snippet and link.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import get_config
from ..env_utils import read_env
from ..oc_models import SearchResult
from .base import SearchProvider


class SerperProvider(SearchProvider):
    name = "serper"

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        cfg = get_config()
        api_key_env = cfg.get("search", {}).get("providers", {}).get("serper", {}).get("api_key_env", "SERPER_API_KEY")
        api_key = read_env(api_key_env)
        if not api_key:
            return []

        base_url = cfg.get("search", {}).get("providers", {}).get("serper", {}).get("base_url", "https://google.serper.dev")
        url = f"{base_url.rstrip('/')}/search"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": min(max_results, 10)},
                )
            if resp.status_code != 200:
                return []

            data = resp.json()
            organic = data.get("organic", [])
            results: list[SearchResult] = []
            for item in organic[:max_results]:
                title = (item.get("title") or "").strip()
                snippet = (item.get("snippet") or "").strip()
                link = (item.get("link") or "").strip()
                if title or snippet:
                    results.append(SearchResult(
                        title=title or "(no title)",
                        url=link,
                        snippet=snippet,
                        source=self.name,
                        query=query,
                    ))
            return results
        except Exception:
            return []

    @classmethod
    def is_available(cls, cfg: dict[str, Any] | None = None) -> bool:
        cfg = cfg or get_config()
        api_key_env = cfg.get("search", {}).get("providers", {}).get("serper", {}).get("api_key_env", "SERPER_API_KEY")
        return bool(read_env(api_key_env))
