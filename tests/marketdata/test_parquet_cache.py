from datetime import datetime

import polars as pl
import pytest

from alphatools.marketdata.api import MarketDataError, load_bars
from alphatools.marketdata.cache.parquet import ParquetBarCache
from alphatools.marketdata.models import BarRequest
from alphatools.marketdata.schema import CANONICAL_SCHEMA


def _fake_bars(symbol="SPY", year=2024, n=5):
    rows = []
    for i in range(n):
        rows.append(
            dict(
                symbol=symbol,
                timestamp=datetime(year, 1, 2 + i),
                open=100.0 + i,
                high=110.0 + i,
                low=95.0 + i,
                close=105.0 + i,
                volume=1000 + i,
                source="yfinance",
                interval="1d",
                adjusted=True,
            )
        )
    return pl.DataFrame(rows, schema=CANONICAL_SCHEMA)


def _request(tmp_path, **kwargs):
    base = dict(
        symbols=["SPY"],
        start="2024-01-01",
        end="2025-01-01",
        cache_dir=tmp_path,
    )
    base.update(kwargs)
    return BarRequest(**base)


def test_path_for_layout(tmp_path):
    cache = ParquetBarCache(tmp_path)
    path = cache.path_for("yfinance", "1d", "spy", 2024)
    assert path == (
        tmp_path
        / "bars"
        / "source=yfinance"
        / "interval=1d"
        / "symbol=SPY"
        / "year=2024"
        / "bars.parquet"
    )


def test_write_then_read_roundtrip(tmp_path):
    cache = ParquetBarCache(tmp_path)
    req = _request(tmp_path)
    cache.write(req, _fake_bars())

    assert cache.path_for("yfinance", "1d", "SPY", 2024).exists()

    out = cache.read(req)
    assert out.height == 5
    assert out.columns == list(CANONICAL_SCHEMA.keys())
    assert out.get_column("symbol").unique().to_list() == ["SPY"]


def test_missing_years(tmp_path):
    cache = ParquetBarCache(tmp_path)
    req = _request(tmp_path, symbols=["SPY", "QQQ"], start="2024-01-01", end="2026-01-01")

    # nothing cached yet
    assert cache.missing_years(req) == {"SPY": [2024, 2025], "QQQ": [2024, 2025]}

    cache.write(req, _fake_bars(symbol="SPY", year=2024))
    assert cache.missing_years(req) == {"SPY": [2025], "QQQ": [2024, 2025]}


def test_write_splits_by_symbol_and_year(tmp_path):
    cache = ParquetBarCache(tmp_path)
    req = _request(tmp_path, symbols=["SPY", "QQQ"], start="2024-01-01", end="2026-01-01")
    bars = pl.concat(
        [
            _fake_bars(symbol="SPY", year=2024),
            _fake_bars(symbol="SPY", year=2025),
            _fake_bars(symbol="QQQ", year=2024),
        ]
    )
    cache.write(req, bars)

    assert cache.path_for("yfinance", "1d", "SPY", 2024).exists()
    assert cache.path_for("yfinance", "1d", "SPY", 2025).exists()
    assert cache.path_for("yfinance", "1d", "QQQ", 2024).exists()
    assert not cache.path_for("yfinance", "1d", "QQQ", 2025).exists()


def test_cache_only_raises_when_missing(tmp_path):
    with pytest.raises(MarketDataError, match="missing partitions"):
        load_bars(
            ["SPY"],
            "2024-01-01",
            "2025-01-01",
            mode="cache_only",
            cache_dir=tmp_path,
        )


def test_cache_only_reads_when_present(tmp_path):
    # Seed the cache directly, then read it back via the public API offline.
    cache = ParquetBarCache(tmp_path)
    req = _request(tmp_path)
    cache.write(req, _fake_bars())

    out = load_bars(
        ["SPY"],
        "2024-01-01",
        "2025-01-01",
        mode="cache_only",
        cache_dir=tmp_path,
    )
    assert out.height == 5
    assert out.get_column("timestamp").min() == datetime(2024, 1, 2)
