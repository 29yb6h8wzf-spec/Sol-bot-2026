"""Offline funding audit regression tests, with FAKE markets and no exchange."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from futures_engine.offline_90day_coverage_gate import COINS
from futures_engine.offline_funding_settlement_audit import (
    DAY_MS, MAX_EVENTS_PER_SYMBOL,
    audit_funding_90_days, hypothetical_position_funding,
)

START_DAY = "2026-08-07"
START_MS = int(datetime(2026, 8, 7, tzinfo=timezone.utc).timestamp()*1000)
END_MS = START_MS + 90*DAY_MS
HOUR_MS = 3_600_000


@pytest.fixture
def fake_records():
    # Deliberately synthetic, 8-hour cadences for the fixture ONLY; the audit
    # never assumes a global 8h schedule (real cadence can change).
    timestamps = [START_MS + day*DAY_MS + hour*HOUR_MS
                  for day in range(90) for hour in (0, 8, 16)]
    records = [{"timestamp_ms": at,
                "funding_rate": "-0.0001" if i % 3 == 0 else "0.0001",
                "mark_price": "100"} for i, at in enumerate(timestamps)]
    sources = {coin: {"exchange": "BINANCE",
                      "symbol": coin,
                      "market": "USDT_M_FUTURES",
                      "dataset": "FUNDING_SETTLEMENTS",
                      "fetched_at_ms": END_MS,
                      "complete_through_ms": END_MS} for coin in COINS}
    return ({coin: deepcopy(records) for coin in COINS},
            {coin: list(timestamps) for coin in COINS}, sources)


def audit(f):
    records, schedule, sources = f
    return audit_funding_90_days(
        start_day=START_DAY, rows_by_symbol=records,
        expected_settlements_by_symbol=schedule,
        provenance_by_symbol=sources, observed_as_of_ms=END_MS)


def funding(f, *, symbol="BTCUSDT", side="long", quantity="1",
            entry_ms=START_MS+7*HOUR_MS, exit_ms=START_MS+9*HOUR_MS,
            report=None):
    records, _, _ = f
    return hypothetical_position_funding(
        audit_report=report if report is not None else audit(f),
        rows_by_symbol=records, symbol=symbol, side=side, quantity=quantity,
        entry_ms=entry_ms, exit_ms=exit_ms)


def test_complete_synthetic_90day_series_is_never_authenticated(fake_records):
    report = audit(fake_records)
    assert report["status"] == "FUNDING_CONTINUITY_COMPLETE_UNAUTHENTICATED"
    assert len(report["symbols"]) == 4
    assert all(x["status"] == "COMPLETE_UNAUTHENTICATED"
               and x["expected_events"] == 270
               and len(x["funding_sha256"]) == 64
               for x in report["symbols"].values())
    assert report["funding_reconciled"] is False
    assert report["source_independently_authenticated"] is False
    assert report["execution_authorized"] is False
    assert report["production_ready"] is False


def test_funding_cadence_is_explicit_not_hardcoded_to_eight_hours(fake_records):
    records, schedule, _ = fake_records
    unusual = START_MS + 4*HOUR_MS
    for coin in COINS:
        schedule[coin].insert(1, unusual)
        records[coin].insert(1, {"timestamp_ms": unusual, "funding_rate": "0.001",
                                 "mark_price": "102"})
    report = audit(fake_records)
    assert report["status"] == "FUNDING_CONTINUITY_COMPLETE_UNAUTHENTICATED"
    assert report["symbols"]["BTCUSDT"]["observed_events"] == 271


def test_missing_single_settlement_blocks_whole_portfolio(fake_records):
    records, _, _ = fake_records
    records["SOLUSDT"].pop(5)
    report = audit(fake_records)
    assert report["status"] == "NOT_ENOUGH_VERIFIED_FUNDING"
    assert report["symbols"]["SOLUSDT"]["status"] == "INCOMPLETE_FUNDING_SETTLEMENTS"


def test_extra_settlement_not_present_in_schedule_fails_closed(fake_records):
    records, _, _ = fake_records
    records["XRPUSDT"].insert(1, {
        "timestamp_ms": START_MS+4*HOUR_MS, "funding_rate": "0.0001",
        "mark_price": "100"})
    report = audit(fake_records)
    assert report["symbols"]["XRPUSDT"]["status"] == "INCOMPLETE_FUNDING_SETTLEMENTS"


def test_duplicate_funding_timestamp_is_invalid_not_reconciled(fake_records):
    records, _, _ = fake_records
    records["BTCUSDT"].insert(2, deepcopy(records["BTCUSDT"][1]))
    report = audit(fake_records)
    assert report["symbols"]["BTCUSDT"] == {
        "status": "INVALID_FUNDING_DATA",
        "reason": "unsorted_or_duplicate_funding"}


def test_wrong_instrument_market_source_blocked(fake_records):
    _, _, source = fake_records
    source["ETHUSDT"]["market"] = "SPOT"
    report = audit(fake_records)
    assert report["symbols"]["ETHUSDT"]["status"] == "UNVERIFIED_FUNDING_SOURCE"


def test_end_before_complete_window_not_accepted(fake_records):
    _, _, sources = fake_records
    sources["SOLUSDT"]["complete_through_ms"] = END_MS-HOUR_MS
    report = audit(fake_records)
    assert report["symbols"]["SOLUSDT"]["status"] == "UNVERIFIED_FUNDING_SOURCE"


def test_future_source_timestamp_not_accepted(fake_records):
    _, _, sources = fake_records
    sources["SOLUSDT"]["fetched_at_ms"] = END_MS+1
    report = audit(fake_records)
    assert report["symbols"]["SOLUSDT"]["status"] == "UNVERIFIED_FUNDING_SOURCE"


@pytest.mark.parametrize("bad", [None, "NaN", float("inf"), True,
                                 "Infinity", "oops", "1.5", "-1.5"])
def test_invalid_funding_rate_fails_closed(fake_records, bad):
    rows, _, _ = fake_records
    rows["XRPUSDT"][0]["funding_rate"] = bad
    report = audit(fake_records)
    assert report["symbols"]["XRPUSDT"]["status"] == "INVALID_FUNDING_DATA"


@pytest.mark.parametrize("bad", [None, "NaN", "-1", "0", True, "Infinity"])
def test_invalid_settlement_mark_price_fails_closed(fake_records, bad):
    rows, _, _ = fake_records
    rows["XRPUSDT"][0]["mark_price"] = bad
    report = audit(fake_records)
    assert report["symbols"]["XRPUSDT"]["status"] == "INVALID_FUNDING_DATA"


def test_no_schedule_is_unknown_even_with_no_events(fake_records):
    rows, schedule, _ = fake_records
    rows["BTCUSDT"] = []
    schedule["BTCUSDT"] = []
    report = audit(fake_records)
    assert report["symbols"]["BTCUSDT"]["status"] == "UNKNOWN_FUNDING_SCHEDULE"
    assert not report["funding_reconciled"]


def test_unsorted_reference_schedule_cannot_claim_complete(fake_records):
    _, schedule, _ = fake_records
    schedule["BTCUSDT"][0:2] = schedule["BTCUSDT"][1::-1]
    report = audit(fake_records)
    assert report["symbols"]["BTCUSDT"]["status"] == "INVALID_FUNDING_SCHEDULE"


def test_long_pays_positive_funding_at_settlement(fake_records):
    result = funding(fake_records)
    assert result["status"] == "HYPOTHETICAL_FUNDING_ONLY"
    assert result["settlements_in_position"] == 1
    assert result["funding_pnl_usdt_unverified"] == "-0.0100"
    assert result["funding_reconciled"] is False


def test_short_receives_positive_funding_at_settlement(fake_records):
    result = funding(fake_records, side="short", quantity="2")
    assert result["funding_pnl_usdt_unverified"] == "0.0200"
    assert not result["orders_sent"]


def test_outside_settlement_holding_window_reports_zero_not_missing(fake_records):
    result = funding(fake_records, entry_ms=START_MS+HOUR_MS,
                     exit_ms=START_MS+2*HOUR_MS)
    assert result["status"] == "HYPOTHETICAL_FUNDING_ONLY"
    assert result["settlements_in_position"] == 0
    assert result["funding_pnl_usdt_unverified"] == "0"


@pytest.mark.parametrize("which", ["entry_ms", "exit_ms"])
def test_settlement_exactly_at_entry_or_exit_is_ambiguous(fake_records, which):
    kwargs = {"entry_ms": START_MS+7*HOUR_MS,
              "exit_ms": START_MS+9*HOUR_MS}
    kwargs[which] = START_MS+8*HOUR_MS
    result = funding(fake_records, **kwargs)
    assert result["status"] == "UNKNOWN_FUNDING"
    assert result["reason"] == "ambiguous_settlement_boundary"
    assert result["orders_sent"] is False


def test_report_or_records_tampering_cannot_invent_funding(fake_records):
    validated = audit(fake_records)
    rows, _, _ = fake_records
    rows["BTCUSDT"][1]["funding_rate"] = "0.30"
    result = funding(fake_records, report=validated)
    assert result["status"] == "UNKNOWN_FUNDING"
    assert result["reason"] == "audited_funding_changed"


def test_incomplete_audit_cannot_calculate_zero_funding(fake_records):
    rows, _, _ = fake_records
    rows["SOLUSDT"].pop()
    result = funding(fake_records, symbol="SOLUSDT")
    assert result["status"] == "UNKNOWN_FUNDING"
    assert result["reason"] == "funding_audit_incomplete"


def test_position_outside_complete_window_is_rejected(fake_records):
    with pytest.raises(ValueError, match="funding_position_outside_history"):
        funding(fake_records, entry_ms=END_MS-1, exit_ms=END_MS+1)


def test_invalid_quantity_must_not_produce_cashflow(fake_records):
    with pytest.raises(ValueError, match="invalid_funding_number"):
        funding(fake_records, quantity="NaN")


def test_cross_coin_input_requirements_are_explicit(fake_records):
    rows, schedule, sources = fake_records
    del sources["XRPUSDT"]
    with pytest.raises(ValueError, match="four_explicit_funding_symbols_required"):
        audit_funding_90_days(
            start_day=START_DAY, rows_by_symbol=rows,
            expected_settlements_by_symbol=schedule,
            provenance_by_symbol=sources, observed_as_of_ms=END_MS)


def test_no_historical_data_available_does_not_claim_a_complete_90_days():
    result = audit_funding_90_days(
        start_day=START_DAY,
        rows_by_symbol={symbol: [] for symbol in COINS},
        expected_settlements_by_symbol={symbol: [] for symbol in COINS},
        provenance_by_symbol={symbol: {} for symbol in COINS},
        observed_as_of_ms=END_MS)
    assert result["status"] == "NOT_ENOUGH_VERIFIED_FUNDING"
    assert result["source_independently_authenticated"] is False


@pytest.mark.parametrize("bad_source_symbol", ["BTCUSDT", "BNBUSDT",
                                               "BTC/USDT:USDT", "", None])
def test_eth_funding_source_must_match_its_exact_coin(fake_records, bad_source_symbol):
    rows, schedule, sources = fake_records
    sources["ETHUSDT"]["symbol"] = bad_source_symbol
    report = audit(fake_records)
    assert report["status"] == "NOT_ENOUGH_VERIFIED_FUNDING"
    assert report["symbols"]["ETHUSDT"]["status"] == (
        "UNVERIFIED_FUNDING_SOURCE")
    assert not report["funding_reconciled"]
    assert not report["execution_authorized"]


def test_funding_provenance_missing_symbol_fails_closed(fake_records):
    _, _, sources = fake_records
    del sources["ETHUSDT"]["symbol"]
    report = audit(fake_records)
    assert report["status"] == "NOT_ENOUGH_VERIFIED_FUNDING"
    assert report["symbols"]["ETHUSDT"]["status"] == (
        "UNVERIFIED_FUNDING_SOURCE")


def test_per_coin_source_identity_is_not_an_authenticity_claim(fake_records):
    report = audit(fake_records)
    assert report["status"] == "FUNDING_CONTINUITY_COMPLETE_UNAUTHENTICATED"
    assert report["source_independently_authenticated"] is False
    assert report["funding_reconciled"] is False
    assert report["production_ready"] is False
