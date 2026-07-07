"""Web search provider factory with automatic fallback.

Priority (when config.search.provider is "auto" or unset):
  1. serper      (if SERPER_API_KEY is set)
  2. tavily      (if TAVILY_API_KEY is set)
  3. searxng     (if a SearXNG base_url is configured)
  4. duckduckgo  (if ddgs package is installed)
  5. bing_scraper (last resort; brittle, may be blocked)
"""

from __future__ import annotations

from typing import Any

from ..config import get_config
from .base import SearchProvider
from .bing_scraper_provider import BingScraperProvider
from .duckduckgo_provider import DuckDuckGoProvider
from .searxng_provider import SearXNGProvider
from .serper_provider import SerperProvider
from .tavily_provider import TavilyProvider

_PROVIDERS: dict[str, type[SearchProvider]] = {
    "serper": SerperProvider,
    "tavily": TavilyProvider,
    "searxng": SearXNGProvider,
    "duckduckgo": DuckDuckGoProvider,
    "bing_scraper": BingScraperProvider,
}

# Preferred order for automatic selection.
_AUTO_PRIORITY = ["serper", "tavily", "searxng", "duckduckgo", "bing_scraper"]


def _get_cfg() -> dict[str, Any]:
    return get_config().get("search", {})


def resolve_provider(cfg: dict[str, Any] | None = None) -> SearchProvider:
    """Return the configured or best available search provider instance."""
    cfg = cfg or _get_cfg()
    explicit = (cfg.get("provider") or "auto").lower()

    if explicit != "auto" and explicit in _PROVIDERS:
        return _PROVIDERS[explicit]()

    for name in _AUTO_PRIORITY:
        cls = _PROVIDERS[name]
        if cls.is_available(cfg):
            return cls()

    # Absolute fallback; is_available always returns True.
    return BingScraperProvider()


def list_providers() -> list[dict[str, Any]]:
    """Return metadata for all registered search providers."""
    cfg = _get_cfg()
    return [
        {
            "name": key,
            "label": {
                "serper": "Serper.dev (Google)",
                "tavily": "Tavily AI Search",
                "searxng": "SearXNG (自建)",
                "duckduckgo": "DuckDuckGo (免费但易挂)",
                "bing_scraper": "Bing 爬虫 (最后手段)",
            }.get(key, key),
            "available": cls.is_available(cfg),
        }
        for key, cls in _PROVIDERS.items()
    ]
