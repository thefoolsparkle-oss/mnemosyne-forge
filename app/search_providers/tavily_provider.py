"""Tavily AI search provider.

Tavily returns search results optimized for LLM context, with title, content,
and URL.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import get_config
from ..env_utils import read_env
from ..oc_models import SearchResult
from .base import SearchProvider


class TavilyProvider(SearchProvider):
    name = "tavily"

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        cfg = get_config()
        api_key_env = cfg.get("search", {}).get("providers", {}).get("tavily", {}).get("api_key_env", "TAVILY_API_KEY")
        api_key = read_env(api_key_env)
        if not api_key:
            return []

        base_url = cfg.get("search", {}).get("providers", {}).get("tavily", {}).get("base_url", "https://api.tavily.com")
        url = f"{base_url.rstrip('/')}/search"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={
                        "api_key": api_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": min(max_results, 10),
                        "include_answer": False,
                    },
                )
            if resp.status_code != 200:
                return []

            data = resp.json()
            raw_results = data.get("results", [])
            results: list[SearchResult] = []
            for item in raw_results[:max_results]:
                title = (item.get("title") or "").strip()
                snippet = (item.get("content") or item.get("snippet") or "").strip()
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
        api_key_env = cfg.get("search", {}).get("providers", {}).get("tavily", {}).get("api_key_env", "TAVILY_API_KEY")
        return bool(read_env(api_key_env))
