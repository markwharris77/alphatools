from datetime import datetime

import pytest
from pydantic import ValidationError

from alphatools.marketdata.models import BarRequest
from alphatools.marketdata.transforms.normalize import normalize_symbols, years_between


def _req(**kwargs):
    base = dict(symbols=["spy"], start="2024-01-01", end="2025-01-01")
    base.update(kwargs)
    return BarRequest(**base)


def test_symbols_uppercased_and_tupled():
    req = _req(symbols=["spy", "qqq"])
    assert req.symbols == ("SPY", "QQQ")


def test_single_string_symbol_allowed():
    assert _req(symbols="spy").symbols == ("SPY",)


def test_empty_symbols_rejected():
    with pytest.raises(ValidationError):
        _req(symbols=[])


def test_end_must_be_after_start():
    with pytest.raises(ValidationError):
        _req(start="2024-01-01", end="2024-01-01")
    with pytest.raises(ValidationError):
        _req(start="2025-01-01", end="2024-01-01")


def test_bad_source_rejected():
    with pytest.raises(ValidationError):
        _req(source="bloomberg")


def test_bad_mode_rejected():
    with pytest.raises(ValidationError):
        _req(mode="nonsense")


def test_bad_interval_rejected():
    with pytest.raises(ValidationError):
        _req(interval="7m")


def test_valid_intervals_accepted():
    for interval in ("1m", "5m", "1h", "1d", "1wk", "3mo"):
        assert _req(interval=interval).interval == interval


def test_is_intraday():
    assert _req(interval="5m").is_intraday is True
    assert _req(interval="1d").is_intraday is False


def test_normalize_symbols_dedupes_and_strips():
    assert normalize_symbols([" spy ", "SPY", "qqq"]) == ("SPY", "QQQ")


def test_years_between_inclusive_start_exclusive_end():
    assert years_between(datetime(2024, 1, 1), datetime(2025, 1, 1)) == [2024]
    assert years_between(datetime(2024, 6, 1), datetime(2025, 6, 1)) == [2024, 2025]
    # end exactly on a year boundary does not include that year
    assert years_between(datetime(2023, 1, 1), datetime(2025, 1, 1)) == [2023, 2024]


def test_request_years_property():
    assert _req(start="2023-06-01", end="2025-01-01").years == [2023, 2024]
