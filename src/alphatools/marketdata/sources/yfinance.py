"""yfinance-backed market data source."""

from __future__ import annotations

import polars as pl

from ..models import BarRequest
from ..schema import empty_bars, enforce_schema
from .base import MarketDataSource

# Map yfinance OHLCV column names onto canonical names.
_COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}


class YFinanceSource(MarketDataSource):
    """Fetch bars from yfinance, one symbol at a time for robustness."""

    name = "yfinance"

    def load_bars(self, request: BarRequest) -> pl.DataFrame:
        import yfinance as yf

        frames: list[pl.DataFrame] = []
        for symbol in request.symbols:
            raw = yf.download(
                symbol,
                start=request.start,
                end=request.end,
                interval=request.interval,
                auto_adjust=request.adjusted,
                progress=False,
                threads=False,
            )
            frame = self._to_canonical(raw, symbol, request)
            if frame is not None and not frame.is_empty():
                frames.append(frame)

        if not frames:
            return empty_bars()
        return pl.concat(frames, how="vertical")

    def _to_canonical(self, raw, symbol: str, request: BarRequest) -> pl.DataFrame | None:
        """Convert a single-symbol pandas result into canonical bars."""
        import pandas as pd

        if raw is None or len(raw) == 0:
            return None

        df = raw.copy()
        # Multiple-symbol style results carry a MultiIndex on columns even for a
        # single ticker; drop the ticker level so we are left with OHLCV names.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()

        # The datetime index becomes the first column ("Date" or "Datetime").
        ts_col = next((c for c in df.columns if c not in _COLUMN_MAP), df.columns[0])
        df = df.rename(columns={ts_col: "timestamp", **_COLUMN_MAP})

        bars = pl.from_pandas(df[["timestamp", *_COLUMN_MAP.values()]])

        # Strip any timezone so timestamps are naive wall-clock values for now.
        ts_dtype = bars.schema["timestamp"]
        if isinstance(ts_dtype, pl.Datetime) and ts_dtype.time_zone is not None:
            bars = bars.with_columns(pl.col("timestamp").dt.replace_time_zone(None))

        bars = bars.with_columns(
            pl.lit(symbol).alias("symbol"),
            pl.lit(self.name).alias("source"),
            pl.lit(request.interval).alias("interval"),
            pl.lit(request.adjusted).alias("adjusted"),
        )
        return enforce_schema(bars)
