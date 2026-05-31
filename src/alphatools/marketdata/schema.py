"""Canonical bar schema shared across the marketdata module."""

from __future__ import annotations

import polars as pl

# Canonical columns, in order, that every bars DataFrame returned by this module
# must expose.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "interval",
    "adjusted",
)

# Canonical Polars dtype for each column. Timestamps are naive (no timezone) for
# now; timezone handling can be layered on later.
CANONICAL_SCHEMA: dict[str, pl.DataType] = {
    "symbol": pl.String(),
    "timestamp": pl.Datetime(time_unit="us"),
    "open": pl.Float64(),
    "high": pl.Float64(),
    "low": pl.Float64(),
    "close": pl.Float64(),
    "volume": pl.Int64(),
    "source": pl.String(),
    "interval": pl.String(),
    "adjusted": pl.Boolean(),
}

# Numeric OHLC columns, handy for validation.
PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")


def empty_bars() -> pl.DataFrame:
    """Return an empty DataFrame carrying the canonical schema."""
    return pl.DataFrame(schema=CANONICAL_SCHEMA)


def enforce_schema(bars: pl.DataFrame) -> pl.DataFrame:
    """Reorder and cast ``bars`` to the canonical column order and dtypes.

    Raises ``KeyError`` (via the select) if a required column is missing; callers
    that want a friendly message should run :func:`validate_bars` first.
    """
    return bars.select([pl.col(name).cast(dtype) for name, dtype in CANONICAL_SCHEMA.items()])
