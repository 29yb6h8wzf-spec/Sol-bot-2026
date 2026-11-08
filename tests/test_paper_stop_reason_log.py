"""Offline-only stop-reason accounting regression tests."""
import json
import pytest
from futures_engine.paper_stop_reason_log import record, reason_for, data_subreason


@pytest.mark.parametrize("reason,signal,condition", [
    ("no_cross", None, "NO_EMA_CROSS"),
    ("rsi_fail", None, "LONG_CROSS_RSI_NOT_BELOW_55"),
    ("rsi_fail", None, "SHORT_CROSS_RSI_NOT_ABOVE_45"),
    ("signal", "long", "LONG_PASSED"),
    ("signal", "short", "SHORT_PASSED"),
])
def test_classifies_signal_reasons(reason, signal, condition):
    assert reason_for(signal, {"condition": condition}) == reason


@pytest.mark.parametrize("message,expected", [
    ("stale futures candles", "stale"),
    ("invalid or gapped futures candles", "gap"),
    ("insufficient closed candles", "insufficient"),
    ("other validation failure", "other"),
])
def test_data_rejection_subreasons(message, expected):
    assert data_subreason(ValueError(message)) == expected


@pytest.mark.parametrize("reason,subreason", [
    ("data_rejected", "stale"),
    ("data_rejected", "gap"),
    ("data_rejected", "insufficient"),
    ("no_cross", None),
    ("rsi_fail", None),
    ("signal", None),
])
def test_daily_counters_persist_and_reopen(tmp_path, reason, subreason):
    path = tmp_path / "btc.audit.json"
    candle = None if reason == "data_rejected" else 900000
    assert record(path, "BTCUSDT", candle, reason, subreason)
    state = json.loads(path.read_text())
    assert state["market"] == "BTCUSDT"
    assert state["days"]
    day = next(iter(state["days"].values()))
    assert day[reason] == 1
    if subreason:
        assert day["data_subreasons"][subreason] == 1
    assert path.stat().st_mode & 0o077 == 0


def test_duplicate_and_out_of_order_candles_are_not_counted(tmp_path):
    path = tmp_path / "btc.audit.json"
    assert record(path, "BTCUSDT", 900000, "no_cross")
    assert record(path, "BTCUSDT", 900000, "signal") is False
    assert record(path, "BTCUSDT", 0, "signal") is False
    assert record(path, "BTCUSDT", 1800000, "rsi_fail")
    state = json.loads(path.read_text())
    day = next(iter(state["days"].values()))
    assert day["no_cross"] == 1
    assert day["signal"] == 0
    assert day["rsi_fail"] == 1


def test_mismatched_market_rejected(tmp_path):
    path = tmp_path / "btc.audit.json"
    record(path, "BTCUSDT", 900000, "signal")
    with pytest.raises(ValueError, match="audit_market_mismatch"):
        record(path, "ETHUSDT", 1800000, "signal")


def test_invalid_reason_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="invalid_stop_reason"):
        record(tmp_path / "x", "BTCUSDT", 900000, "made_up")
