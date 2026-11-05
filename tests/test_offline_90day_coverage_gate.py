"""Synthetic offline 90-day 5m coverage gates (not actual exchange history)."""
from datetime import datetime, timezone
from copy import deepcopy

import pytest

from futures_engine.offline_90day_coverage_gate import (
    COINS, DAYS, EXPECTED_BARS, INTERVAL_MS,
    TRAIN_DAYS, TEST_DAYS, MAX_EVAL_BARS, inspect_90_days,
    classify_historical_signal,
)

START = "2026-08-07"
START_MS = int(datetime(2026, 8, 7, tzinfo=timezone.utc).timestamp()*1000)
END_MS = START_MS + DAYS*86400000


@pytest.fixture
def dataset():
    # Deliberately reuse the same immutable-equivalent fake candles for each
    # symbol. This tests ONLY continuity, never upstream authenticity/PnL.
    data = [(START_MS + i*INTERVAL_MS, "100", "101", "99", "100")
            for i in range(EXPECTED_BARS)]
    metadata = {"exchange": "BINANCE", "market": "USDT_M_FUTURES",
                "interval": "5m", "fetched_at_ms": END_MS,
                "closed_through_ms": END_MS}
    return ({coin: data for coin in COINS},
            {coin: dict(metadata) for coin in COINS})


def run(data, provenance, **kwargs):
    return inspect_90_days(start_day=START,
                           candles_by_symbol=data,
                           provenance_by_symbol=provenance,
                           evaluated_as_of_ms=END_MS, **kwargs)


def test_90_full_days_four_assets_prove_continuity_only(dataset):
    data, p = dataset
    result = run(data, p)
    assert result["expected_days"] == 90
    assert result["bars_per_symbol"] == EXPECTED_BARS == 25_920
    assert result["status"] == "OHLCV_CONTINUITY_COMPLETE_PROVENANCE_UNAUTHENTICATED"
    assert all(item["status"] == "COMPLETE_UNAUTHENTICATED"
               for item in result["symbols"].values())
    assert len({r["history_sha256"] for r in result["symbols"].values()}) == 1
    assert not result["source_independently_authenticated"]
    assert not result["funding_reconciled"]
    assert not result["production_ready"]
    assert not result["orders_sent"]
    assert not result["execution_authorized"]


def test_train_test_split_is_63_days_then_27_with_48_bar_embargo(dataset):
    data, p = dataset
    r = run(data, p)
    split = START_MS + TRAIN_DAYS*86400000
    assert (TRAIN_DAYS, TEST_DAYS) == (63, 27)
    assert r["split_utc_ms"] == split
    assert r["first_eligible_test_signal_open_ms"] == split
    # Signal opens in train, closes on the next bar, and a 48-bar exit
    # cannot observe even one candle from the test period.
    last = r["last_eligible_train_signal_open_ms"]
    assert last + (MAX_EVAL_BARS + 1)*INTERVAL_MS == split
    assert r["last_eligible_test_signal_open_ms"] + 49*INTERVAL_MS == END_MS
    assert r["train_test_leakage_guard"] is True


def test_holding_window_90_minutes_respects_distinct_18bar_embargo(dataset):
    data, p = dataset
    r = run(data, p, max_evaluation_bars=18)
    assert r["last_eligible_train_signal_open_ms"] + 19*INTERVAL_MS == r["split_utc_ms"]
    assert r["last_eligible_train_signal_open_ms"] > (
        r["split_utc_ms"] - 49*INTERVAL_MS)


def test_89_day_window_is_incomplete_not_optimistic(dataset):
    data, p = dataset
    data["SOLUSDT"] = data["SOLUSDT"][:-288]
    r = run(data, p)
    assert r["status"] == "NOT_ENOUGH_VERIFIED_HISTORY"
    assert r["symbols"]["SOLUSDT"]["observed_bars"] == EXPECTED_BARS - 288
    assert r["symbols"]["SOLUSDT"]["status"] == "INCOMPLETE"


def test_timestamp_gap_with_same_count_fails_closed(dataset):
    data, p = dataset
    damaged = list(data["BTCUSDT"])
    row = damaged[900]
    damaged[900] = (row[0] + INTERVAL_MS, *row[1:])
    data["BTCUSDT"] = damaged
    r = run(data, p)
    assert r["status"] == "NOT_ENOUGH_VERIFIED_HISTORY"
    assert r["symbols"]["BTCUSDT"]["first_bad_offset"] == 900
    assert r["symbols"]["BTCUSDT"]["reason"] == "timestamp_gap_duplicate_or_unclosed"


def test_nan_price_fails_closed(dataset):
    data, p = dataset
    damaged = list(data["ETHUSDT"])
    t, op, high, low, close = damaged[400]
    damaged[400] = (t, op, "NaN", low, close)
    data["ETHUSDT"] = damaged
    r = run(data, p)
    assert r["symbols"]["ETHUSDT"]["reason"] == "invalid_candle_prices"


def test_invalid_high_low_fails_closed(dataset):
    data, p = dataset
    damaged = list(data["ETHUSDT"])
    t, op, high, low, close = damaged[401]
    damaged[401] = (t, op, "98", low, close)
    data["ETHUSDT"] = damaged
    r = run(data, p)
    assert r["symbols"]["ETHUSDT"]["reason"] == "invalid_candle_range"


def test_missing_one_coin_never_reports_ready(dataset):
    data, p = dataset
    del data["XRPUSDT"]
    with pytest.raises(ValueError, match="four_explicit_futures_symbols_required"):
        run(data, p)


def test_spot_masquerading_as_futures_blocked(dataset):
    data, p = dataset
    p["BTCUSDT"]["market"] = "SPOT"
    r = run(data, p)
    assert r["status"] == "NOT_ENOUGH_VERIFIED_HISTORY"
    assert r["symbols"]["BTCUSDT"]["status"] == "UNVERIFIED_PROVENANCE"


def test_claimed_complete_time_before_end_is_rejected(dataset):
    data, p = dataset
    p["SOLUSDT"]["closed_through_ms"] = END_MS - INTERVAL_MS
    r = run(data, p)
    assert r["symbols"]["SOLUSDT"]["status"] == "UNVERIFIED_PROVENANCE"


def test_cannot_claim_90_days_before_all_days_are_closed(dataset):
    data, p = dataset
    with pytest.raises(ValueError, match="incomplete_full_utc_days"):
        inspect_90_days(start_day=START, candles_by_symbol=data,
            provenance_by_symbol=p, evaluated_as_of_ms=END_MS-1)


@pytest.mark.parametrize("invalid", [0,-1,True,False,48.0,49,"48",None])
def test_invalid_eval_window_rejected(dataset, invalid):
    data, p = dataset
    with pytest.raises(ValueError, match="invalid_evaluation_horizon"):
        run(data, p, max_evaluation_bars=invalid)


def test_untrusted_fetch_time_after_audit_time_blocked(dataset):
    data, p = dataset
    p["XRPUSDT"]["fetched_at_ms"] = END_MS+1
    r = run(data, p)
    assert r["symbols"]["XRPUSDT"]["status"] == "UNVERIFIED_PROVENANCE"


def test_no_fabricated_funding_evidence_or_live_edge(dataset):
    data, p = dataset
    r = run(data, p)
    assert r["funding_reconciled"] is False
    assert r["source_independently_authenticated"] is False
    assert r["production_ready"] is False
    assert "pnl" not in str(r).lower()


def test_signal_classifier_explicitly_enforces_train_embargo_and_test(dataset):
    data, p = dataset
    r = run(data, p)
    classify = lambda t: classify_historical_signal(t, r)["status"]
    assert classify(START_MS) == "OFFLINE_TRAIN_ONLY"
    assert classify(r["last_eligible_train_signal_open_ms"]) == "OFFLINE_TRAIN_ONLY"
    assert classify(r["last_eligible_train_signal_open_ms"] + INTERVAL_MS) == (
        "EXCLUDED_TRAIN_TEST_EMBARGO")
    assert classify(r["split_utc_ms"] - INTERVAL_MS) == (
        "EXCLUDED_TRAIN_TEST_EMBARGO")
    assert classify(r["first_eligible_test_signal_open_ms"]) == (
        "OFFLINE_TEST_ONLY")
    assert classify(r["last_eligible_test_signal_open_ms"]) == (
        "OFFLINE_TEST_ONLY")
    assert classify(r["last_eligible_test_signal_open_ms"] + INTERVAL_MS) == (
        "EXCLUDED_OUTSIDE_FULL_WINDOW")
    assert classify(START_MS-INTERVAL_MS) == "EXCLUDED_OUTSIDE_FULL_WINDOW"


def test_signal_classifier_blocks_incomplete_history_not_fake_ready():
    r = classify_historical_signal(START_MS, {
        "status": "NOT_ENOUGH_VERIFIED_HISTORY"})
    assert r["status"] == "BLOCKED_INCOMPLETE_DATA"
    assert r["orders_sent"] is False


@pytest.mark.parametrize("timestamp", [None, False, True, 1.2, "0", -1,
                                        START_MS+1])
def test_signal_classifier_rejects_invalid_signal_time(timestamp):
    with pytest.raises(ValueError, match="signal_timestamp"):
        classify_historical_signal(timestamp, {})


def test_signal_classifier_rejects_tampered_split_boundaries(dataset):
    data, p = dataset
    result = run(data, p)
    damaged = dict(result)
    damaged["last_eligible_train_signal_open_ms"] += INTERVAL_MS
    with pytest.raises(ValueError, match="invalid_split_boundaries"):
        classify_historical_signal(START_MS, damaged)
