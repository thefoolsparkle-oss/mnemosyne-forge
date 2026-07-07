"""Image generation provider factory."""

from __future__ import annotations

from typing import Any

from .base import ImageProvider
from .custom_provider import CustomProvider
from .openai_provider import OpenAIProvider
from .pollinations_provider import PollinationsProvider
from .seedream_provider import SeedreamProvider
from .stability_provider import StabilityProvider


_PROVIDERS: dict[str, type[ImageProvider]] = {
    "stability": StabilityProvider,
    "openai": OpenAIProvider,
    "seedream": SeedreamProvider,
    "pollinations": PollinationsProvider,
    "custom": CustomProvider,
}


def get_provider(name: str) -> ImageProvider:
    """Return an instance of the named image provider."""
    name = (name or "pollinations").lower()
    if name not in _PROVIDERS:
        raise ValueError(
            f"Unknown image provider '{name}'. Available: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[name]()


def list_providers() -> list[dict[str, Any]]:
    """Return metadata for all registered providers."""
    return [
        {
            "name": key,
            "label": {
                "stability": "Stability AI",
                "openai": "OpenAI DALL-E",
                "seedream": "Seedream (火山方舟)",
                "pollinations": "Pollinations（免费默认）",
                "custom": "其他（自定义）",
            }.get(key, key),
            "requires_api_key": cls.requires_api_key(),
            "supports_negative_prompt": cls.supports_negative_prompt(),
        }
        for key, cls in _PROVIDERS.items()
    ]

