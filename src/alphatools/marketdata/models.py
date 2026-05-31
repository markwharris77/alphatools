"""Request model for the marketdata module."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Modes supported by ``load_bars``.
ALLOWED_MODES: frozenset[str] = frozenset({"cache_first", "cache_only", "refresh", "source_only"})

# Sources supported for now.
ALLOWED_SOURCES: frozenset[str] = frozenset({"yfinance"})

# yfinance intervals we recognise.
ALLOWED_INTERVALS: frozenset[str] = frozenset(
    {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}
)

# Intervals finer than one day. These get special, range-clamped fetching because
# yfinance only serves a short recent window of intraday history.
INTRADAY_INTERVALS: frozenset[str] = frozenset({"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"})


def _to_naive_datetime(value: str | date | datetime) -> datetime:
    """Coerce a date-like input into a naive ``datetime``."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        # ``fromisoformat`` handles "2024-01-01" and "2024-01-01T09:30:00".
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=None)
    raise TypeError(f"Unsupported date type: {type(value)!r}")


class BarRequest(BaseModel):
    """Validated description of a bars request.

    ``start`` is inclusive and ``end`` is exclusive throughout the module.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    interval: str = "1d"
    source: str = "yfinance"
    adjusted: bool = True
    mode: str = "cache_first"
    cache_dir: Path | None = None

    @field_validator("symbols", mode="before")
    @classmethod
    def _normalize_symbols(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, (list, tuple)):
            raise TypeError("symbols must be a string or a list/tuple of strings")
        symbols = tuple(str(s).strip().upper() for s in value if str(s).strip())
        if not symbols:
            raise ValueError("symbols must be a non-empty list of tickers")
        return symbols

    @field_validator("start", "end", mode="before")
    @classmethod
    def _coerce_dates(cls, value: object) -> datetime:
        return _to_naive_datetime(value)  # type: ignore[arg-type]

    @field_validator("interval")
    @classmethod
    def _check_interval(cls, value: str) -> str:
        if value not in ALLOWED_INTERVALS:
            raise ValueError(
                f"interval {value!r} not recognised; expected one of {sorted(ALLOWED_INTERVALS)}"
            )
        return value

    @field_validator("source")
    @classmethod
    def _check_source(cls, value: str) -> str:
        if value not in ALLOWED_SOURCES:
            raise ValueError(
                f"source {value!r} not supported; expected one of {sorted(ALLOWED_SOURCES)}"
            )
        return value

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, value: str) -> str:
        if value not in ALLOWED_MODES:
            raise ValueError(
                f"mode {value!r} not supported; expected one of {sorted(ALLOWED_MODES)}"
            )
        return value

    @field_validator("cache_dir", mode="before")
    @classmethod
    def _coerce_cache_dir(cls, value: object) -> Path | None:
        if value is None:
            return None
        return Path(value)  # type: ignore[arg-type]

    @model_validator(mode="after")
    def _check_range(self) -> BarRequest:
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be after start ({self.start})")
        return self

    @property
    def is_intraday(self) -> bool:
        return self.interval in INTRADAY_INTERVALS

    @property
    def years(self) -> list[int]:
        """Calendar years overlapped by ``[start, end)``."""
        from .transforms.normalize import years_between

        return years_between(self.start, self.end)
