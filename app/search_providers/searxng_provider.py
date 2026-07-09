"""SearXNG self-hosted search provider.

SearXNG exposes a JSON API at /search?q=...&format=json. It is free if you
run your own instance.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import get_config
from ..oc_models import SearchResult
from .base import SearchProvider


class SearXNGProvider(SearchProvider):
    name = "searxng"

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        cfg = get_config()
        base_url = cfg.get("search", {}).get("providers", {}).get("searxng", {}).get("base_url", "")
        if not base_url:
            return []

        try:
            params = {"q": query, "format": "json", "pageno": 1}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{base_url.rstrip('/')}/search", params=params)
            if resp.status_code != 200:
                return []

            data = resp.json()
            raw_results = data.get("results", [])
            results: list[SearchResult] = []
            for item in raw_results[:max_results]:
                title = (item.get("title") or "").strip()
                snippet = (item.get("content") or "").strip()
                url = (item.get("url") or "").strip()
                if title or snippet:
                    results.append(SearchResult(
                        title=title or "(no title)",
                        url=url,
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
        base_url = cfg.get("search", {}).get("providers", {}).get("searxng", {}).get("base_url", "")
        return bool(base_url)
