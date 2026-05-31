"""Validation of canonical bars DataFrames."""

from __future__ import annotations

import polars as pl

from .schema import CANONICAL_COLUMNS, PRICE_COLUMNS


class MarketDataValidationError(Exception):
    """Raised when a bars DataFrame violates the canonical contract."""


def validate_bars(bars: pl.DataFrame) -> None:
    """Validate a canonical bars DataFrame in place; raise on serious issues.

    An empty DataFrame is considered valid (the source simply returned no data).
    """
    missing = [c for c in CANONICAL_COLUMNS if c not in bars.columns]
    if missing:
        raise MarketDataValidationError(f"missing required columns: {missing}")

    if bars.is_empty():
        return

    # Null checks on the columns that must always be present.
    for col in ("symbol", "timestamp", "close"):
        n_null = bars.get_column(col).null_count()
        if n_null:
            raise MarketDataValidationError(f"{n_null} null value(s) in required column {col!r}")

    # Duplicate (symbol, timestamp) rows.
    n_dupes = bars.select("symbol", "timestamp").is_duplicated().sum()
    if n_dupes:
        raise MarketDataValidationError(f"{n_dupes} duplicate (symbol, timestamp) row(s)")

    # Negative prices / volume.
    for col in (*PRICE_COLUMNS, "volume"):
        n_neg = bars.filter(pl.col(col) < 0).height
        if n_neg:
            raise MarketDataValidationError(f"{n_neg} negative value(s) in column {col!r}")

    # OHLC consistency. high must be the max and low the min of the bar.
    checks = {
        "high < low": pl.col("high") < pl.col("low"),
        "high < open": pl.col("high") < pl.col("open"),
        "high < close": pl.col("high") < pl.col("close"),
        "low > open": pl.col("low") > pl.col("open"),
        "low > close": pl.col("low") > pl.col("close"),
    }
    for label, predicate in checks.items():
        n_bad = bars.filter(predicate).height
        if n_bad:
            raise MarketDataValidationError(f"{n_bad} row(s) violate OHLC rule: {label}")
