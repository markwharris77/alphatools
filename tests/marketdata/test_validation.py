from datetime import datetime

import polars as pl
import pytest

from alphatools.marketdata.schema import empty_bars
from alphatools.marketdata.validation import MarketDataValidationError, validate_bars


def _good_row(**overrides):
    row = dict(
        symbol="SPY",
        timestamp=datetime(2024, 1, 2),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=1000,
        source="yfinance",
        interval="1d",
        adjusted=True,
    )
    row.update(overrides)
    return row


def _frame(*rows):
    return pl.DataFrame(list(rows))


def test_good_frame_passes():
    validate_bars(_frame(_good_row(), _good_row(timestamp=datetime(2024, 1, 3))))


def test_empty_frame_passes():
    validate_bars(empty_bars())


def test_missing_column_raises():
    df = _frame(_good_row()).drop("close")
    with pytest.raises(MarketDataValidationError, match="missing required columns"):
        validate_bars(df)


def test_duplicate_rows_raise():
    with pytest.raises(MarketDataValidationError, match="duplicate"):
        validate_bars(_frame(_good_row(), _good_row()))


def test_null_close_raises():
    with pytest.raises(MarketDataValidationError, match="null"):
        validate_bars(_frame(_good_row(close=None)))


@pytest.mark.parametrize(
    "overrides",
    [
        dict(high=90.0),  # high < low
        dict(open=120.0),  # high < open
        dict(close=120.0),  # high < close
        dict(low=101.0, open=100.0),  # low > open
        dict(low=106.0, close=105.0, high=110.0),  # low > close
    ],
)
def test_bad_ohlc_raises(overrides):
    with pytest.raises(MarketDataValidationError):
        validate_bars(_frame(_good_row(**overrides)))


@pytest.mark.parametrize("col", ["open", "high", "low", "close", "volume"])
def test_negative_values_raise(col):
    with pytest.raises(MarketDataValidationError, match="negative"):
        validate_bars(_frame(_good_row(**{col: -1})))
