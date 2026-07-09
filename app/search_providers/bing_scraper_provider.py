"""Direct Bing HTML scraper fallback.

This is a last-resort provider that fetches Bing search result pages and
parses the HTML. It is brittle and may break if Bing changes its markup or
blocks the request. Use an API provider when possible.
"""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

from ..oc_models import SearchResult
from .base import SearchProvider


_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class BingScraperProvider(SearchProvider):
    name = "bing_scraper"

    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        import random

        headers = {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(
                    "https://www.bing.com/search",
                    params={"q": query, "count": min(max_results * 2, 30)},
                    headers=headers,
                )
            if resp.status_code != 200:
                return []

            text = resp.text
            # Bing result items are usually wrapped in <li class="b_algo">
            results: list[SearchResult] = []
            for match in re.finditer(r'<li class="b_algo"[^>]*>(.*?)</li>', text, re.DOTALL | re.IGNORECASE):
                block = match.group(1)
                title_match = re.search(r'<h2[^>]*>.*?<a[^>]*>(.*?)</a>.*?</h2>', block, re.DOTALL | re.IGNORECASE)
                url_match = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"', block, re.DOTALL | re.IGNORECASE)
                snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL | re.IGNORECASE)

                title = html.unescape(re.sub(r'<[^>]+>', '', title_match.group(1) if title_match else "")).strip()
                snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet_match.group(1) if snippet_match else "")).strip()
                url = html.unescape(url_match.group(1) if url_match else "").strip()

                if title or snippet:
                    results.append(SearchResult(
                        title=title or "(no title)",
                        url=url,
                        snippet=snippet,
                        source=self.name,
                        query=query,
                    ))
                if len(results) >= max_results:
                    break

            return results
        except Exception:
            return []

    @classmethod
    def is_available(cls, cfg: dict[str, Any] | None = None) -> bool:
        return True
