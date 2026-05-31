"""Market data sources."""

from .base import MarketDataSource
from .yfinance import YFinanceSource

__all__ = ["MarketDataSource", "YFinanceSource"]


def get_source(name: str) -> MarketDataSource:
    """Return a source instance by name."""
    if name == "yfinance":
        return YFinanceSource()
    raise ValueError(f"unknown source: {name!r}")
