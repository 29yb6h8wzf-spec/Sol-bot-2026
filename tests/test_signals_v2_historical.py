"""Historical replay provenance, closed-bar alignment and no-future tests."""
from dataclasses import replace
import pytest
from signals_v2.contracts import DataRejected, FIVE_MINUTES_MS, MINUTE_MS
from signals_v2.historical import historical_rows, replay_snapshot

BASE = 1_800_000_000_000


def feeds(n=70):
    five = [[BASE+i*FIVE_MINUTES_MS, 100, 102, 98, 101, 5] for i in range(n)]
    one = []
    for i in range(n):
        for j in range(5):
            one.append([BASE+i*FIVE_MINUTES_MS+j*MINUTE_MS,
                        100, 102 if j == 0 else 101,
                        98 if j == 0 else 100,
                        101 if j == 4 else 100, 1])
    return five, one


def test_historical_replay_asof_uses_only_closed_bars():
    five, one = feeds()
    f = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m = historical_rows("SOLUSDT", MINUTE_MS, one, source="fixture")
    decision = BASE+69*FIVE_MINUTES_MS
    snap = replay_snapshot(f, m, decision_ms=decision)
    assert len(snap.five_minute) == 64
    assert len(snap.one_minute) == 10
    assert snap.five_minute[-1].open_ms == BASE+68*FIVE_MINUTES_MS
    assert snap.one_minute[-1].available_at_ms == decision
    assert f.availability_assumption == "HISTORICAL_CANDLE_CLOSE_RECONSTRUCTED"
    assert len(f.sha256_digest) == 64


def test_future_bar_is_excluded_not_backfilled():
    five, one = feeds()
    f = historical_rows("XRPUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m = historical_rows("XRPUSDT", MINUTE_MS, one, source="fixture")
    d = BASE+69*FIVE_MINUTES_MS
    a = replay_snapshot(f, m, decision_ms=d)
    five.append([BASE+70*FIVE_MINUTES_MS, 100, 200, 1, 150, 10])
    one.extend([[BASE+70*FIVE_MINUTES_MS+j*MINUTE_MS, 100, 200, 1, 150, 2] for j in range(5)])
    f2 = historical_rows("XRPUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m2 = historical_rows("XRPUSDT", MINUTE_MS, one, source="fixture")
    assert replay_snapshot(f2, m2, decision_ms=d) == a


def test_reject_historical_gaps_duplicates_and_future_decisions():
    five, one = feeds()
    with pytest.raises(DataRejected, match="historical_gap_or_duplicate"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, five[:3]+five[4:], source="fixture")
    with pytest.raises(DataRejected, match="historical_gap_or_duplicate"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, five[:3]+[five[2]]+five[3:], source="fixture")
    f = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m = historical_rows("SOLUSDT", MINUTE_MS, one, source="fixture")
    with pytest.raises(DataRejected, match="insufficient_history"):
        replay_snapshot(f, m, decision_ms=BASE+10*FIVE_MINUTES_MS)


def test_hash_is_content_sensitive_and_provenance_is_explicit():
    five, _ = feeds()
    f = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="Binance public archive")
    five[0][4] = 100.5
    g = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="Binance public archive")
    assert f.sha256_digest != g.sha256_digest
    assert f.source == g.source
    with pytest.raises(DataRejected, match="missing_provenance"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="")


def test_reject_mismatched_symbol_and_fake_observation_time():
    five, one = feeds()
    f = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m = historical_rows("XRPUSDT", MINUTE_MS, one, source="fixture")
    with pytest.raises(DataRejected, match="historical_pair_mismatch"):
        replay_snapshot(f, m, decision_ms=BASE+69*FIVE_MINUTES_MS)
    with pytest.raises(DataRejected, match="historical_availability_not_close"):
        replace(f, bars=(replace(f.bars[0], available_at_ms=f.bars[0].available_at_ms+1),)+f.bars[1:])


@pytest.mark.parametrize("five_lookback,one_lookback", [
    (0, 10), (-1, 10), (64, 0), (64, -2),
    (True, 10), (64, False), (1.5, 10), (64, "10"),
])
def test_replay_rejects_invalid_lookbacks(five_lookback, one_lookback):
    five, one = feeds()
    f = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m = historical_rows("SOLUSDT", MINUTE_MS, one, source="fixture")
    with pytest.raises(DataRejected, match="invalid_replay_lookback"):
        replay_snapshot(f, m, decision_ms=BASE+69*FIVE_MINUTES_MS,
                        lookback_five=five_lookback, lookback_one=one_lookback)


@pytest.mark.parametrize("extra", [[], [123], ["untracked"]])
def test_reject_noncanonical_historical_row_width(extra):
    five, _ = feeds()
    five[0] = five[0] + extra
    if not extra:
        five[0] = five[0][:-1]
    with pytest.raises(DataRejected, match="invalid_historical_row"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
