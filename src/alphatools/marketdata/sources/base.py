"""Abstract base class for market data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl

from ..models import BarRequest


class MarketDataSource(ABC):
    """A backing provider of canonical bars."""

    name: str

    @abstractmethod
    def load_bars(self, request: BarRequest) -> pl.DataFrame:
        """Fetch bars for ``request`` and return them in the canonical schema.

        Implementations fetch exactly ``[request.start, request.end)`` and return
        an empty canonical DataFrame when the provider has no data. Range filtering
        and caching are handled by the caller.
        """
        ...
