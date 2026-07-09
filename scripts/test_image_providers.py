"""Tests for image generation provider abstraction.

These tests mock HTTP calls and do not hit real image APIs.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from app import config as app_config
from app.image_providers import get_provider, list_providers
from app.image_providers.custom_provider import CustomProvider
from app.image_providers.openai_provider import OpenAIProvider
from app.image_providers.pollinations_provider import PollinationsProvider
from app.image_providers.seedream_provider import SeedreamProvider
from app.image_providers.stability_provider import StabilityProvider
from app.oc_models import OCDraft

# Use a stub config so the providers can read image.providers settings.
app_config._config_cache = {
    "app": {"database_path": "data/forge.db", "export_dir": "exports"},
    "image": {
        "provider": "pollinations",
        "providers": {
            "pollinations": {"width": 1024, "height": 1024},
            "stability": {"api_key_env": "STABILITY_API_KEY", "model": "sd3.5-large", "aspect_ratio": "1:1"},
            "openai": {"api_key_env": "OPENAI_API_KEY", "model": "dall-e-3", "size": "1024x1024", "quality": "standard"},
            "seedream": {"api_key_env": "SEEDREAM_API_KEY", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "seedream-3-0-t2i-250722", "size": "1024x1024"},
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


def _draft() -> OCDraft:
    return OCDraft(name="Test Character", appearance="silver hair, blue eyes")


def test_list_providers() -> None:
    providers = list_providers()
    names = {p["name"] for p in providers}
    assert names == {"stability", "openai", "seedream", "pollinations", "custom"}
    pollinations = next(p for p in providers if p["name"] == "pollinations")
    assert pollinations["requires_api_key"] is False


def test_get_provider() -> None:
    assert isinstance(get_provider("stability"), StabilityProvider)
    assert isinstance(get_provider("openai"), OpenAIProvider)
    assert isinstance(get_provider("seedream"), SeedreamProvider)
    assert isinstance(get_provider("pollinations"), PollinationsProvider)
    assert isinstance(get_provider("custom"), CustomProvider)


@pytest.mark.anyio
async def test_stability_provider_success(monkeypatch) -> None:
    async def fake_post(*args, **kwargs):
        image_b64 = base64.b64encode(b"fake_image").decode()
        return _FakeResponse(200, {"image": image_b64, "seed": 123})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = StabilityProvider()
    result = await provider.generate(_draft(), "anime portrait", "prompt", "negative")
    assert result["ok"] is True
    assert result["seed"] == 123
    assert result["image_path"].endswith(".png")


@pytest.mark.anyio
async def test_stability_provider_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("STABILITY_API_KEY", raising=False)
    app_config._config_cache["image"]["providers"]["stability"]["api_key_env"] = "MISSING_KEY_ENV_XYZ"
    try:
        provider = StabilityProvider()
        result = await provider.generate(_draft(), "anime portrait", "prompt", "negative")
        assert result["ok"] is False
        assert "API Key" in result["error"] or "未配置" in result["error"]
    finally:
        app_config._config_cache["image"]["providers"]["stability"]["api_key_env"] = "STABILITY_API_KEY"


@pytest.mark.anyio
async def test_openai_provider_success(monkeypatch) -> None:
    async def fake_post(*args, **kwargs):
        image_b64 = base64.b64encode(b"fake_image").decode()
        return _FakeResponse(200, {"created": 456, "data": [{"b64_json": image_b64}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = OpenAIProvider()
    result = await provider.generate(_draft(), "anime portrait", "prompt", "negative")
    assert result["ok"] is True
    assert result["seed"] == 456
    assert result["image_path"].endswith(".png")


@pytest.mark.anyio
async def test_pollinations_provider_success(monkeypatch) -> None:
    async def fake_get(*args, **kwargs):
        return _FakeResponse(200, content=b"fake_image")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    provider = PollinationsProvider()
    result = await provider.generate(_draft(), "anime portrait", "prompt", "negative")
    assert result["ok"] is True
    assert result["image_path"].endswith(".png")


@pytest.mark.anyio
async def test_custom_provider_requires_fields() -> None:
    provider = CustomProvider()
    result = await provider.generate(_draft(), "anime portrait", "prompt", "negative")
    assert result["ok"] is False
    assert "base_url" in result["error"]


@pytest.mark.anyio
async def test_seedream_provider_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("SEEDREAM_API_KEY", raising=False)
    app_config._config_cache["image"]["providers"]["seedream"]["api_key_env"] = "MISSING_SEEDREAM_KEY"
    try:
        provider = SeedreamProvider()
        result = await provider.generate(_draft(), "anime portrait", "prompt", "negative")
        assert result["ok"] is False
        assert "API Key" in result["error"] or "未配置" in result["error"]
    finally:
        app_config._config_cache["image"]["providers"]["seedream"]["api_key_env"] = "SEEDREAM_API_KEY"


@pytest.mark.anyio
async def test_seedream_provider_success(monkeypatch) -> None:
    async def fake_post(*args, **kwargs):
        image_b64 = base64.b64encode(b"fake_image").decode()
        return _FakeResponse(200, {"created": 321, "data": [{"b64_json": image_b64}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = SeedreamProvider()
    monkeypatch.setenv("SEEDREAM_API_KEY", "fake_seedream_key")
    result = await provider.generate(_draft(), "anime portrait", "prompt", "negative")
    assert result["ok"] is True
    assert result["seed"] == 321
    assert result["image_path"].endswith(".png")


@pytest.mark.anyio
async def test_custom_provider_success(monkeypatch) -> None:
    async def fake_post(*args, **kwargs):
        image_b64 = base64.b64encode(b"fake_image").decode()
        return _FakeResponse(200, {"created": 789, "data": [{"b64_json": image_b64}]})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = CustomProvider()
    result = await provider.generate(
        _draft(),
        "anime portrait",
        "prompt",
        "negative",
        base_url="https://example.com/v1",
        model="my-model",
        api_key="secret",
    )
    assert result["ok"] is True
    assert result["seed"] == 789


def main() -> None:
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    main()
