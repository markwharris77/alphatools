"""Public entry point: ``load_bars``."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import polars as pl

from .cache.parquet import ParquetBarCache
from .models import BarRequest
from .sources import MarketDataSource, get_source
from .transforms.normalize import filter_range, normalize_bars
from .validation import validate_bars

# Default cache root, project-local so research data lives beside the repo.
_DEFAULT_CACHE_SUBPATH = (".alphatools", "cache", "marketdata")


class MarketDataError(Exception):
    """Raised when requested data cannot be served from cache or source."""


def load_bars(
    symbols: list[str] | tuple[str, ...] | str,
    start: str | datetime | date,
    end: str | datetime | date,
    interval: str = "1d",
    source: str = "yfinance",
    adjusted: bool = True,
    mode: str = "cache_first",
    cache_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Load canonical OHLCV bars, using a local parquet cache.

    ``start`` is inclusive and ``end`` is exclusive. The returned Polars
    DataFrame carries the canonical schema (see :mod:`alphatools.marketdata.schema`)
    and is sorted by ``(symbol, timestamp)``.

    Raises :class:`MarketDataError` if the requested data is available from
    neither the cache nor the source.
    """
    request = BarRequest(
        symbols=symbols,
        start=start,
        end=end,
        interval=interval,
        source=source,
        adjusted=adjusted,
        mode=mode,
        cache_dir=cache_dir,
    )

    cache = ParquetBarCache(_resolve_cache_root(request.cache_dir))
    src = get_source(request.source)

    if request.mode == "source_only":
        result = _load_source_only(request, src)
    elif request.mode == "cache_only":
        result = _load_cache_only(request, cache)
    elif request.mode == "refresh":
        result = _load_refresh(request, src, cache)
    else:  # cache_first
        result = _load_cache_first(request, src, cache)

    _guard_non_empty(result, request)
    return result


# --- mode handlers ---------------------------------------------------------


def _load_source_only(request: BarRequest, src: MarketDataSource) -> pl.DataFrame:
    bars = src.load_bars(request)
    validate_bars(bars)
    return filter_range(normalize_bars(bars), request.start, request.end)


def _load_cache_only(request: BarRequest, cache: ParquetBarCache) -> pl.DataFrame:
    missing = cache.missing_years(request)
    if missing:
        raise MarketDataError(
            "cache_only request is missing partitions: "
            + _format_missing(missing, request.interval)
        )
    bars = cache.read(request)
    return filter_range(bars, request.start, request.end)


def _load_refresh(
    request: BarRequest, src: MarketDataSource, cache: ParquetBarCache
) -> pl.DataFrame:
    year_to_symbols = {year: list(request.symbols) for year in request.years}
    _fetch_and_cache(request, src, cache, year_to_symbols)
    bars = cache.read(request)
    return filter_range(bars, request.start, request.end)


def _load_cache_first(
    request: BarRequest, src: MarketDataSource, cache: ParquetBarCache
) -> pl.DataFrame:
    missing = cache.missing_years(request)
    if missing:
        year_to_symbols: dict[int, list[str]] = {}
        for symbol, years in missing.items():
            for year in years:
                year_to_symbols.setdefault(year, []).append(symbol)
        _fetch_and_cache(request, src, cache, year_to_symbols)
    bars = cache.read(request)
    return filter_range(bars, request.start, request.end)


# --- fetching helpers ------------------------------------------------------


def _fetch_and_cache(
    request: BarRequest,
    src: MarketDataSource,
    cache: ParquetBarCache,
    year_to_symbols: dict[int, list[str]],
) -> None:
    """Fetch each year's symbols from the source and write them to the cache."""
    for year, symbols in year_to_symbols.items():
        lo, hi = _fetch_window(request, year)
        sub = request.model_copy(update={"symbols": tuple(symbols), "start": lo, "end": hi})
        bars = src.load_bars(sub)
        validate_bars(bars)
        cache.write(sub, bars)


def _fetch_window(request: BarRequest, year: int) -> tuple[datetime, datetime]:
    """Date window to fetch for a missing ``year``.

    Daily+ intervals fetch the whole calendar year. Intraday intervals are clamped
    to the requested range so we never expand a valid recent request into a
    full-year request that falls outside yfinance's intraday window.
    """
    year_start = datetime(year, 1, 1)
    year_end = datetime(year + 1, 1, 1)
    if request.is_intraday:
        return max(year_start, request.start), min(year_end, request.end)
    return year_start, year_end


# --- misc helpers ----------------------------------------------------------


def _resolve_cache_root(cache_dir: Path | None) -> Path:
    if cache_dir is not None:
        return cache_dir
    return Path.cwd().joinpath(*_DEFAULT_CACHE_SUBPATH)


def _format_missing(missing: dict[str, list[int]], interval: str) -> str:
    parts = [f"{sym} {interval} year(s) {years}" for sym, years in sorted(missing.items())]
    return "; ".join(parts)


def _guard_non_empty(result: pl.DataFrame, request: BarRequest) -> None:
    """Raise if any requested symbol produced no rows."""
    present = (
        set(result.get_column("symbol").unique().to_list()) if not result.is_empty() else set()
    )
    empty_symbols = [s for s in request.symbols if s not in present]
    if empty_symbols:
        raise MarketDataError(
            f"no data available for {empty_symbols} "
            f"(interval={request.interval}, range=[{request.start}, {request.end})) "
            f"in cache or from source {request.source!r}"
        )
