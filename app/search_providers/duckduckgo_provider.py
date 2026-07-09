"""DuckDuckGo search provider.

Uses the ddgs package to scrape DuckDuckGo text results. Free but rate-limited
and occasionally blocked.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..oc_models import SearchResult
from .base import SearchProvider


def _ddg_search_sync(query: str, max_results: int) -> list[SearchResult]:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results: list[SearchResult] = []
            for r in ddgs.text(query, max_results=max_results):
                title = r.get("title", "").strip()
                snippet = r.get("body", "").strip()
                url = r.get("href", "").strip()
                if title or snippet:
                    results.append(SearchResult(
                        title=title or "(no title)",
                        url=url,
                        snippet=snippet,
                        source="duckduckgo",
                        query=query,
                    ))
            return results
    except Exception:
        return []


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        return await asyncio.to_thread(_ddg_search_sync, query, max_results)

    @classmethod
    def is_available(cls, cfg: dict[str, Any] | None = None) -> bool:
        try:
            from ddgs import DDGS  # noqa: F401
            return True
        except Exception:
            return False
