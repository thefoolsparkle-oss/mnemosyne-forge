"""Base class and factory for image generation providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..oc_models import OCDraft


class ImageProvider(ABC):
    """Abstract image generation provider.

    Implementations must handle their own API authentication and HTTP calls.
    The generate() method receives the full draft and prompt/negative prompt
    and returns a normalized result dict.
    """

    name: str = ""

    @abstractmethod
    async def generate(
        self,
        draft: OCDraft,
        style: str,
        prompt: str,
        negative_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate one image.

        Returns:
            {
                "ok": bool,
                "image_path": str | None,
                "prompt": str,
                "negative_prompt": str,
                "seed": int | None,
                "error": str | None,
            }
        """
        raise NotImplementedError

    @classmethod
    def requires_api_key(cls) -> bool:
        """Return True if this provider cannot work without an API key."""
        return True

    @classmethod
    def supports_negative_prompt(cls) -> bool:
        """Return True if the provider accepts a negative prompt."""
        return True


class ImageProviderError(Exception):
    """Raised when an image provider fails to generate an image."""
