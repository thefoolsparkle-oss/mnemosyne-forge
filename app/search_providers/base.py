"""Base class for web search providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..oc_models import SearchResult


class SearchProvider(ABC):
    """Abstract web search provider.

    Implementations must execute a query and return a normalized list of
    SearchResult objects. All network I/O should be async.
    """

    name: str = ""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5, **kwargs: Any) -> list[SearchResult]:
        """Run a single search query.

        Returns a list of SearchResult. The provider name should be set in
        each result's `source` field.
        """
        raise NotImplementedError

    @classmethod
    def is_available(cls, cfg: dict[str, Any] | None = None) -> bool:
        """Return True if this provider can be used in the current environment.

        Subclasses should check for required API keys, installed packages, or
        configured endpoints. The default implementation returns True.
        """
        return True
