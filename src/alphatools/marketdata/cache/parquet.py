"""Year-partitioned parquet cache for canonical bars."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from ..models import BarRequest
from ..schema import empty_bars
from ..transforms.normalize import normalize_bars

# Filename written inside each year partition.
_FILE_NAME = "bars.parquet"


class ParquetBarCache:
    """Read/write canonical bars partitioned by source/interval/symbol/year.

    Layout::

        <root>/bars/source=<source>/interval=<interval>/symbol=<SYM>/year=<YYYY>/bars.parquet
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, source: str, interval: str, symbol: str, year: int) -> Path:
        return (
            self.root
            / "bars"
            / f"source={source}"
            / f"interval={interval}"
            / f"symbol={symbol.upper()}"
            / f"year={year}"
            / _FILE_NAME
        )

    def missing_years(self, request: BarRequest) -> dict[str, list[int]]:
        """Map each symbol to the requested years that have no parquet file yet."""
        years = request.years
        missing: dict[str, list[int]] = {}
        for symbol in request.symbols:
            absent = [
                year
                for year in years
                if not self.path_for(request.source, request.interval, symbol, year).exists()
            ]
            if absent:
                missing[symbol] = absent
        return missing

    def read(self, request: BarRequest) -> pl.DataFrame:
        """Read all cached partitions for the request's symbols/years.

        Returns canonical, normalised bars (not yet filtered to the exact range).
        """
        frames: list[pl.DataFrame] = []
        for symbol in request.symbols:
            for year in request.years:
                path = self.path_for(request.source, request.interval, symbol, year)
                if path.exists():
                    frames.append(pl.read_parquet(path))
        if not frames:
            return empty_bars()
        return normalize_bars(pl.concat(frames, how="vertical"))

    def write(self, request: BarRequest, bars: pl.DataFrame) -> None:
        """Split ``bars`` by (symbol, year) and write each partition (overwrite)."""
        if bars.is_empty():
            return
        bars = normalize_bars(bars)
        partitioned = bars.with_columns(pl.col("timestamp").dt.year().alias("__year"))
        for (symbol, year), group in partitioned.group_by(["symbol", "__year"]):
            path = self.path_for(request.source, request.interval, str(symbol), int(year))
            path.parent.mkdir(parents=True, exist_ok=True)
            group.drop("__year").write_parquet(path)
