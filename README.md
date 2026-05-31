# alphatools

A local-first quant research toolkit. The first module, `alphatools.marketdata`,
pulls OHLCV bars from yfinance, normalises them into a canonical schema, validates
them, and caches them as year-partitioned parquet so repeat calls are fast and
offline.

## Install

```bash
uv sync
```

## Market data usage

```python
from alphatools.marketdata import load_bars

bars = load_bars(["SPY", "RSP"], "2024-01-01", "2025-01-01")
print(bars.head())
```

`load_bars` returns a [Polars](https://pola.rs) DataFrame with the canonical
schema:

| column    | type      |
| --------- | --------- |
| symbol    | str       |
| timestamp | datetime  |
| open      | float     |
| high      | float     |
| low       | float     |
| close     | float     |
| volume    | int       |
| source    | str       |
| interval  | str       |
| adjusted  | bool      |

### Signature

```python
load_bars(
    symbols,                 # list/tuple/str of tickers (uppercased)
    start,                   # inclusive; str | date | datetime
    end,                     # exclusive; str | date | datetime
    interval="1d",           # 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
    source="yfinance",
    adjusted=True,
    mode="cache_first",
    cache_dir=None,          # defaults to ./.alphatools/cache/marketdata
)
```

### Modes

- `cache_first` — read cache, fetch only missing yearly partitions, write them,
  return the requested range.
- `cache_only` — never hit the network; raise if required partitions are missing.
- `refresh` — refetch the overlapping years and overwrite the cache.
- `source_only` — fetch from the source and return, without writing the cache.

Dates are half-open: `start <= timestamp < end`. If requested data is available
from neither the cache nor the source, `load_bars` raises `MarketDataError`.

The cache is partitioned deterministically:

```
.alphatools/cache/marketdata/bars/
  source=yfinance/interval=1d/symbol=SPY/year=2024/bars.parquet
```

> Note: yfinance only serves a short recent window of intraday history (e.g.
> ~60 days for `5m`), so intraday requests must fall within that window.

## Development

```bash
uv run ruff format .
uv run ruff check .
uv run pytest          # offline tests; live API tests are marked `integration`
```
