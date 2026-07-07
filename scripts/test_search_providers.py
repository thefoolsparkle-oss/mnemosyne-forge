"""Tests for web search provider abstraction.

These tests mock HTTP calls and do not hit real search engines.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from app import config as app_config
from app.search_providers import (
    DuckDuckGoProvider,
    SerperProvider,
    TavilyProvider,
    list_providers,
    resolve_provider,
)
from app.search_providers.bing_scraper_provider import BingScraperProvider

app_config._config_cache = {
    "app": {"database_path": "data/forge.db", "export_dir": "exports"},
    "search": {
        "provider": "auto",
        "max_queries": 3,
        "results_per_query": 3,
        "max_results": 6,
        "providers": {
            "serper": {"api_key_env": "SERPER_API_KEY", "base_url": "https://google.serper.dev"},
            "tavily": {"api_key_env": "TAVILY_API_KEY", "base_url": "https://api.tavily.com"},
            "searxng": {"base_url": ""},
        },
    },
}


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None, text="", content=b""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text
        self.content = content

    def json(self):
        return self._json


def test_list_providers() -> None:
    providers = list_providers()
    names = {p["name"] for p in providers}
    assert names == {"serper", "tavily", "searxng", "duckduckgo", "bing_scraper"}


def test_resolve_provider_falls_back_to_bing_scraper(monkeypatch) -> None:
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    provider = resolve_provider(app_config._config_cache["search"])
    assert isinstance(provider, (DuckDuckGoProvider, BingScraperProvider))


@pytest.mark.anyio
async def test_serper_provider_success(monkeypatch) -> None:
    async def fake_post(*args, **kwargs):
        return _FakeResponse(200, {
            "organic": [
                {"title": "T1", "snippet": "This is a long enough snippet for testing.", "link": "https://example.com/1"},
                {"title": "T2", "snippet": "Another long enough snippet for testing.", "link": "https://example.com/2"},
            ]
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setenv("SERPER_API_KEY", "fake")

    provider = SerperProvider()
    results = await provider.search("test", max_results=2)
    assert len(results) == 2
    assert results[0].source == "serper"
    assert "example.com" in results[0].url


@pytest.mark.anyio
async def test_serper_provider_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    provider = SerperProvider()
    results = await provider.search("test")
    assert results == []


@pytest.mark.anyio
async def test_tavily_provider_success(monkeypatch) -> None:
    async def fake_post(*args, **kwargs):
        return _FakeResponse(200, {
            "results": [
                {"title": "T1", "content": "This is a long enough snippet for testing.", "url": "https://example.com/1"},
            ]
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setenv("TAVILY_API_KEY", "fake")

    provider = TavilyProvider()
    results = await provider.search("test", max_results=2)
    assert len(results) == 1
    assert results[0].source == "tavily"


@pytest.mark.anyio
async def test_bing_scraper_provider_parses_html(monkeypatch) -> None:
    html = '''
    <li class="b_algo"><h2><a href="https://example.com/1">Title One</a></h2><p>This is a long enough snippet for testing.</p></li>
    <li class="b_algo"><h2><a href="https://example.com/2">Title Two</a></h2><p>Another long enough snippet for testing.</p></li>
    '''

    async def fake_get(*args, **kwargs):
        return _FakeResponse(200, text=html)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    provider = BingScraperProvider()
    results = await provider.search("test", max_results=2)
    assert len(results) == 2
    assert results[0].source == "bing_scraper"
    assert "Title One" in results[0].title


def main() -> None:
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    main()
