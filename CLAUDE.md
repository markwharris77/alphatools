# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`alphatools` is a local-first quant research toolkit (Python 3.13, managed with `uv`). Today it contains one module, `alphatools.marketdata`; the package is laid out to grow into sibling modules (`metadata`, `features`, `targets`, `validate`, `backtest`, `pricing`) under `src/alphatools/`. Scope is intentionally limited to data loading/caching — no trading or backtesting yet.

## Commands

```bash
uv sync                          # install runtime + dev deps into .venv
uv run ruff format .             # format
uv run ruff check .              # lint (also: --fix)
uv run pytest                    # offline test suite (integration tests deselected by default)
uv run pytest tests/marketdata/test_models.py::test_is_intraday   # single test
uv run pytest -m integration     # run the live-yfinance tests (network required)
```

Tests that hit the live yfinance API must be marked `@pytest.mark.integration`; `addopts` in `pyproject.toml` deselects that marker so the default run stays offline. There are currently no integration tests checked in — all existing tests use synthetic Polars frames or stubbed sources.

## Architecture

The marketdata module is a layered pipeline behind a single public function, `load_bars` (`src/alphatools/marketdata/api.py`). Data flows: **request model → cache check → source fetch (only for gaps) → validate → normalize → year-partitioned parquet → filter to exact range**.

- **`models.py` — `BarRequest`**: the frozen Pydantic contract every layer passes around. It normalizes inputs at construction time: symbols → uppercased tuple, `start`/`end` → naive `datetime`, and allow-lists for source/mode/interval. `start` is inclusive, `end` is exclusive everywhere. Sub-requests are derived with `request.model_copy(update=...)`, never by mutation.
- **`api.py`** orchestrates the four modes (`cache_first`, `cache_only`, `refresh`, `source_only`) — see Key behaviors below. Mode handlers are small private functions; `_fetch_and_cache` inverts the per-symbol "missing years" map into per-year sub-requests.
- **`sources/`**: `MarketDataSource` ABC + `YFinanceSource`. `get_source(name)` is the factory. Sources fetch *exactly* `[start, end)` and return canonical bars (or empty); they do not filter or cache.
- **`cache/parquet.py` — `ParquetBarCache`**: deterministic layout `bars/source=<s>/interval=<i>/symbol=<SYM>/year=<Y>/bars.parquet`. Granularity is **yearly partitions** — a partition either exists or it's "missing" and gets refetched whole.
- **`transforms/normalize.py`**: pure helpers (`normalize_symbols`, `years_between`, `filter_range`, `normalize_bars`). `normalize_bars` enforces the canonical schema, sorts by `(symbol, timestamp)`, and dedupes keeping the latest row.
- **`schema.py`**: the single source of truth for the canonical 10-column schema (`CANONICAL_SCHEMA`) and dtype casting (`enforce_schema`). Every returned/cached frame conforms to it.
- **`validation.py`**: `validate_bars` raises `MarketDataValidationError` on structural/OHLC problems but **treats an empty frame as valid** — emptiness is handled at the API layer, not here.

## Key behaviors and conventions

- **Polars everywhere; pandas only at the yfinance boundary.** `YFinanceSource` converts pandas → Polars immediately (handling multi-index columns and stripping tz to naive wall-clock). Don't let pandas leak into core code.
- **Raise on missing data, not silent empties.** `_guard_non_empty` in `api.py` raises `MarketDataError` if any requested symbol yields zero rows from cache+source. This deliberately overrides the "return empty rather than crash" idea — `validate_bars` allows empty, but `load_bars` does not return empty for a requested symbol.
- **Intraday fetch ranges are clamped.** yfinance only serves a short recent window of intraday history (~60 days for `5m`). `_fetch_window` fetches the full calendar year for daily+ intervals but clamps sub-daily intervals (see `INTRADAY_INTERVALS`) to the requested range, so a valid recent intraday request isn't expanded into an out-of-window full-year fetch. Consequence: an intraday year partition may hold only part of that year — a known, accepted simplification.
- **Cache default** is project-local: `./.alphatools/cache/marketdata/` (gitignored). Pass `cache_dir` to override; tests always pass a `tmp_path`.

## Adding a new source

Implement `MarketDataSource` (return canonical bars for exactly the requested range), register it in `get_source` (`sources/__init__.py`), and add it to `ALLOWED_SOURCES` in `models.py`. The cache and API layers are source-agnostic.
