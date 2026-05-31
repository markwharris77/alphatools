I have initialized a Python package project with uv called `alphatools`.

I want you to implement the first useful module: a reusable market data pulling and parquet caching layer using yfinance as the only backing source for now.

High-level goal:
Build `alphatools.marketdata`, a local-first market data module for quant research. It should let me call one function from notebooks:

    from alphatools.marketdata import load_bars

    bars = load_bars(
        symbols=["SPY", "RSP", "QQQ"],
        start="2024-01-01",
        end="2024-12-31",
        interval="1d",
    )

The function should:
1. Accept symbols, date range, interval, source, adjusted flag, cache mode, and optional cache directory.
2. Use yfinance as the source for now.
3. Normalize all provider data into one canonical schema.
4. Validate the data.
5. Store it as parquet in a local cache.
6. Reuse the parquet cache on future calls.
7. Fetch only missing yearly partitions when mode is cache_first.
8. Return a Polars DataFrame.
9. Include a sample notebook showing how to use it.

Use `src/alphatools/marketdata/` as the package folder, not `data/`, because later I may add separate modules for metadata, features, targets, validation, pricing, etc.

Expected package structure:

src/alphatools/
  __init__.py

  marketdata/
    __init__.py
    api.py
    models.py
    schema.py
    validation.py

    cache/
      __init__.py
      parquet.py

    sources/
      __init__.py
      base.py
      yfinance.py

    transforms/
      __init__.py
      normalize.py

notebooks/
  001_marketdata_loader.ipynb

tests/
  marketdata/
    test_models.py
    test_validation.py
    test_parquet_cache.py

Dependencies I expect:
- polars
- pyarrow
- yfinance
- pydantic
- platformdirs maybe, if useful
- pytest for tests

Do not use pandas throughout the core code except where yfinance returns pandas objects. Convert to Polars as early as possible.

Canonical bar schema:
Every returned dataframe should have these columns:

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str
    interval: str
    adjusted: bool

Optional later columns like vwap can be added later, but not required now.

Implement this public API:

    load_bars(
        symbols: list[str] | tuple[str, ...],
        start: str | datetime | date,
        end: str | datetime | date,
        interval: str = "1d",
        source: str = "yfinance",
        adjusted: bool = True,
        mode: str = "cache_first",
        cache_dir: str | Path | None = None,
    ) -> pl.DataFrame

Supported modes:
- "cache_first": read from cache where possible, fetch missing yearly partitions, write cache, return complete requested range.
- "cache_only": never call yfinance; return only cached data. Raise a clear error if required partitions are missing.
- "refresh": ignore existing cached partitions, refetch requested yearly partitions, overwrite cache.
- "source_only": fetch from yfinance and return data, but do not write to cache.

Important behavior:
- Normalize symbols to uppercase.
- Sort by symbol, timestamp.
- Deduplicate by symbol, timestamp, keeping the latest row.
- Filter returned data exactly to requested start <= timestamp < end.
- Cache path should be deterministic and partitioned by source, interval, symbol, and year.

Recommended cache path:

    .alphatools/cache/marketdata/bars/
      source=yfinance/
        interval=1d/
          symbol=SPY/
            year=2024/
              bars.parquet

Implement a `BarRequest` model using Pydantic or dataclasses. It should include:
- symbols
- start
- end
- interval
- source
- adjusted
- mode
- cache_dir

It should validate:
- symbols is non-empty
- end > start
- source must currently be "yfinance"
- mode must be one of the allowed modes
- interval can be a string, but preferably validate common yfinance intervals:
  1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo

Implement `MarketDataSource` base class:

    class MarketDataSource(ABC):
        name: str

        @abstractmethod
        def load_bars(self, request: BarRequest) -> pl.DataFrame:
            ...

Implement `YFinanceSource`.

Important yfinance details:
- yfinance returns pandas DataFrames.
- For one symbol, columns are usually Open/High/Low/Close/Volume and Date or Datetime index.
- For multiple symbols, yfinance can return multi-index columns and be annoying.
- To keep the implementation simple and robust, fetch one symbol at a time in a loop.
- Use `yf.download(...)`.
- Use `auto_adjust=request.adjusted`.
- Use `progress=False`.
- Convert each symbol’s result to Polars and append symbol/source/interval/adjusted columns.
- Concatenate all symbols.

Validation:
Create `validate_bars(bars: pl.DataFrame) -> None`.

It should raise a custom `MarketDataValidationError` for serious issues:
- missing required columns
- duplicate symbol/timestamp rows
- null symbol/timestamp/close
- high < low
- high < open
- high < close
- low > open
- low > close
- negative open/high/low/close/volume

It should allow an empty dataframe only if source returned no data, but load_bars should generally return empty rather than crashing unless cache_only requires missing data.

Parquet cache:
Create a `ParquetBarCache` class with methods something like:

    class ParquetBarCache:
        def __init__(self, root: Path): ...

        def read(self, request: BarRequest) -> pl.DataFrame: ...
        def write(self, request: BarRequest, bars: pl.DataFrame) -> None: ...
        def missing_years(self, request: BarRequest) -> dict[str, list[int]]: ...
        def path_for(self, source: str, interval: str, symbol: str, year: int) -> Path: ...

Simplify cache granularity to yearly partitions:
- If the request overlaps 2024 and 2025, check for year=2024 and year=2025 parquet files for each symbol.
- If a year file is missing, fetch that full calendar year for that symbol.
- For current year, still use yearly partition. Simplicity is fine for now.
- When writing, split bars by symbol/year and write `bars.parquet`.

For cache_first:
- Determine missing years per symbol.
- Fetch missing years from yfinance using sub-requests.
- Write them to cache.
- Read all needed data from cache.
- Filter to exact requested date range.

For refresh:
- Fetch all years overlapping request.
- Overwrite relevant parquet files.
- Read/return exact requested range.

For cache_only:
- If any required year partition is missing, raise a clear error listing missing symbols/years.
- Otherwise read and return exact requested range.

For source_only:
- Fetch exact requested range from yfinance.
- Validate and return. Do not write.

Be careful with date boundaries:
- The API should treat `start` inclusive and `end` exclusive.
- If user asks start="2024-01-01", end="2025-01-01", return timestamps >= 2024-01-01 and < 2025-01-01.
- For yearly partition fetches, fetch from YYYY-01-01 to YYYY+1-01-01.
- Use naive datetimes for now, but keep the code clean enough to support timezone handling later.

Add helper functions:
- `years_between(start, end) -> list[int]`
- `normalize_symbols(symbols) -> tuple[str, ...]`
- maybe `filter_range(bars, start, end)`

Notebook:
Create `notebooks/001_marketdata_loader.ipynb` that demonstrates:
1. Importing `load_bars`.
2. Loading SPY/RSP/QQQ daily bars for 2024.
3. Showing the returned schema/head.
4. Calling the same load again to demonstrate cache reuse.
5. Loading 5m bars for a smaller date range.
6. Creating a simple wide close dataframe.
7. Computing simple daily returns for SPY and RSP.
8. Computing SPY minus RSP return divergence.
9. Plotting or displaying a small table is enough. Do not overdo visualization.

Also add a simple README section explaining usage:

    from alphatools.marketdata import load_bars

    bars = load_bars(["SPY", "RSP"], "2024-01-01", "2025-01-01")

Testing:
Add unit tests for:
- BarRequest validation
- year calculation
- validation catching bad OHLC data
- cache path generation
- writing and reading a small fake Polars dataframe from parquet
- cache_only raising when missing data

Avoid tests that require live network for now, or mark them as integration/skipped by default. Use fake dataframes for cache tests.

Code style:
- Type annotations.
- Clear exceptions.
- Small functions.
- Avoid overengineering.
- No live trading, no backtesting yet.
- This module should only handle market data loading and caching.

After implementing, run:
    uv run ruff format .
    uv run ruff check .
    uv run pytest

If pyproject lacks dependencies, add them with uv-compatible project config.

this is future structure so you can undestand where were going:

alphatools/
  pyproject.toml
  README.md
  uv.lock

  src/
    alphatools/
      __init__.py

      marketdata/
        __init__.py
        api.py
        models.py
        schema.py
        validation.py

        cache/
          __init__.py
          parquet.py

        sources/
          __init__.py
          base.py
          yfinance.py

        transforms/
          __init__.py
          normalize.py

      metadata/
        __init__.py

      features/
        __init__.py

      targets/
        __init__.py

      validate/
        __init__.py

      backtest/
        __init__.py

      pricing/
        __init__.py

  notebooks/
    001_marketdata_loader.ipynb

  tests/
    marketdata/
      test_models.py
      test_validation.py
      test_parquet_cache.py

  .alphatools/
    cache/
      marketdata/