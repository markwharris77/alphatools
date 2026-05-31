"""Small, pure helpers for normalising bars and request inputs."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import polars as pl

from ..schema import enforce_schema


def normalize_symbols(symbols: str | Iterable[str]) -> tuple[str, ...]:
    """Uppercase, strip, drop blanks, and de-duplicate (order-preserving)."""
    if isinstance(symbols, str):
        symbols = [symbols]
    seen: dict[str, None] = {}
    for raw in symbols:
        sym = str(raw).strip().upper()
        if sym:
            seen.setdefault(sym, None)
    return tuple(seen)


def years_between(start: datetime, end: datetime) -> list[int]:
    """Calendar years overlapped by the half-open interval ``[start, end)``.

    ``end`` is exclusive: a request ending exactly at ``YYYY-01-01`` does not
    include year ``YYYY``.
    """
    last_year = end.year
    # If end falls exactly on a year boundary it belongs to the previous year.
    if end.month == 1 and end.day == 1 and end.hour == 0 and end.minute == 0 and end.second == 0:
        last_year -= 1
    last_year = max(last_year, start.year)
    return list(range(start.year, last_year + 1))


def filter_range(bars: pl.DataFrame, start: datetime, end: datetime) -> pl.DataFrame:
    """Keep rows with ``start <= timestamp < end`` (start inclusive, end exclusive)."""
    if bars.is_empty():
        return bars
    return bars.filter((pl.col("timestamp") >= start) & (pl.col("timestamp") < end))


def normalize_bars(bars: pl.DataFrame) -> pl.DataFrame:
    """Cast to the canonical schema, sort, and de-duplicate.

    Sorts by ``(symbol, timestamp)`` and drops duplicate ``(symbol, timestamp)``
    rows, keeping the last occurrence (treated as the most recent write).
    """
    if bars.is_empty():
        return enforce_schema(bars)
    bars = enforce_schema(bars)
    bars = bars.sort(["symbol", "timestamp"])
    bars = bars.unique(subset=["symbol", "timestamp"], keep="last", maintain_order=True)
    return bars
