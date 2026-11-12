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


def test_reject_historical_digest_tampering():
    five, _ = feeds()
    original = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    with pytest.raises(DataRejected, match="historical_digest_mismatch"):
        replace(original, sha256_digest="0" * 64)
    altered = replace(original.bars[0], close=100.5)
    with pytest.raises(DataRejected, match="historical_digest_mismatch"):
        replace(original, bars=(altered,) + original.bars[1:])


@pytest.mark.parametrize("bad_digest", ["x" * 64, "A" * 64, "0" * 63, "0" * 65, 123])
def test_reject_malformed_historical_digest(bad_digest):
    five, _ = feeds()
    original = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    with pytest.raises(DataRejected, match="invalid_historical_digest"):
        replace(original, sha256_digest=bad_digest)


@pytest.mark.parametrize("bad_source", ["", "   ", None, 123])
def test_reject_invalid_historical_source_metadata(bad_source):
    five, _ = feeds()
    original = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    with pytest.raises(DataRejected, match="missing_provenance"):
        replace(original, source=bad_source)


@pytest.mark.parametrize("field_index", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("boolean_value", [True, False])
def test_reject_boolean_historical_ohlcv(field_index, boolean_value):
    five, _ = feeds()
    five[0][field_index] = boolean_value
    with pytest.raises(DataRejected, match="invalid_historical_row"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")


@pytest.mark.parametrize("bad_rows", [None, 42, True, "not rows", b"rows", {"rows": []}])
def test_reject_invalid_historical_feed_containers(bad_rows):
    with pytest.raises(DataRejected, match="invalid_historical_rows"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, bad_rows, source="fixture")


@pytest.mark.parametrize("container", [list, lambda bars: bars[:]])
def test_reject_mutable_historical_bar_containers(container):
    five, _ = feeds()
    original = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    with pytest.raises(DataRejected, match="invalid_historical_bars_container"):
        replace(original, bars=container(list(original.bars)))


@pytest.mark.parametrize("bad_bar", [None, "not a candle", 123, {"open_ms": BASE}])
def test_reject_non_candle_historical_bar(bad_bar):
    five, _ = feeds()
    original = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    with pytest.raises(DataRejected, match="invalid_historical_bar"):
        replace(original, bars=(bad_bar,) + original.bars[1:])


@pytest.mark.parametrize("bad_value", ["101", b"101", None, object(), True, False])
def test_reject_implicit_historical_price_coercion(bad_value):
    five, _ = feeds()
    five[0][4] = bad_value
    with pytest.raises(DataRejected, match="invalid_historical_row"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")


def test_numeric_ohlcv_int_and_float_remain_accepted():
    five, _ = feeds()
    five[0][4] = 101.25
    bars = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    assert bars.bars[0].close == 101.25


@pytest.mark.parametrize("unordered", [set, frozenset])
def test_reject_unordered_historical_feeds(unordered):
    five, _ = feeds()
    rows = unordered(tuple(row) for row in five)
    with pytest.raises(DataRejected, match="invalid_historical_rows"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, rows, source="fixture")


@pytest.mark.parametrize("bad_decision", [None, True, False, 0, -1, 1.5, "1800000000000"])
def test_replay_rejects_invalid_decision_time(bad_decision):
    five, one = feeds()
    f = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m = historical_rows("SOLUSDT", MINUTE_MS, one, source="fixture")
    with pytest.raises(DataRejected, match="invalid_decision_time"):
        replay_snapshot(f, m, decision_ms=bad_decision)


def test_replay_at_exact_close_boundary_does_not_use_unclosed_five_minute_bar():
    five, one = feeds()
    f = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m = historical_rows("SOLUSDT", MINUTE_MS, one, source="fixture")
    boundary = BASE + 69 * FIVE_MINUTES_MS
    before = replay_snapshot(f, m, decision_ms=boundary - 1)
    at = replay_snapshot(f, m, decision_ms=boundary)
    assert before.five_minute[-1].available_at_ms == boundary - FIVE_MINUTES_MS
    assert at.five_minute[-1].available_at_ms == boundary
    assert before.one_minute[-1].available_at_ms == boundary - MINUTE_MS
    assert at.one_minute[-1].available_at_ms == boundary


@pytest.mark.parametrize("bad_symbol", [None, 42, [], {}, {"SOLUSDT"}, b"SOLUSDT"])
def test_historical_rows_reject_nonstring_symbol(bad_symbol):
    five, _ = feeds()
    with pytest.raises(DataRejected, match="invalid_symbol_or_timeframe"):
        historical_rows(bad_symbol, FIVE_MINUTES_MS, five, source="fixture")


@pytest.mark.parametrize("bad_timeframe", [
    float(FIVE_MINUTES_MS), float(MINUTE_MS), True, None, "300000", [], {},
])
def test_historical_rows_reject_noninteger_timeframe(bad_timeframe):
    five, _ = feeds()
    with pytest.raises(DataRejected, match="invalid_symbol_or_timeframe"):
        historical_rows("SOLUSDT", bad_timeframe, five, source="fixture")


@pytest.mark.parametrize("field,value,error", [
    ("symbol", [], "unsupported_symbol"),
    ("symbol", None, "unsupported_symbol"),
    ("timeframe_ms", float(FIVE_MINUTES_MS), "unsupported_timeframe"),
    ("timeframe_ms", None, "unsupported_timeframe"),
])
def test_historical_bars_reject_noncanonical_metadata_types(field, value, error):
    five, _ = feeds()
    original = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    with pytest.raises(DataRejected, match=error):
        replace(original, **{field: value})


@pytest.mark.parametrize("bad_pair", [
    (None, None), ({"symbol": "SOLUSDT"}, None), ("SOLUSDT", None),
    (None, 123),
])
def test_replay_rejects_non_historical_pair(bad_pair):
    with pytest.raises(DataRejected, match="invalid_historical_pair"):
        replay_snapshot(*bad_pair, decision_ms=BASE + 69 * FIVE_MINUTES_MS)


def test_replay_rejects_one_invalid_feed_without_attribute_errors():
    five, one = feeds()
    f = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    m = historical_rows("SOLUSDT", MINUTE_MS, one, source="fixture")
    with pytest.raises(DataRejected, match="invalid_historical_pair"):
        replay_snapshot(f, object(), decision_ms=BASE + 69 * FIVE_MINUTES_MS)
    with pytest.raises(DataRejected, match="invalid_historical_pair"):
        replay_snapshot(object(), m, decision_ms=BASE + 69 * FIVE_MINUTES_MS)


@pytest.mark.parametrize("failure", [TypeError, ValueError, RuntimeError, OSError, EOFError, OverflowError])
def test_historical_feed_stream_failure_is_rejected(failure):
    five, _ = feeds()

    def broken_archive():
        yield from five[:5]
        raise failure("archive interrupted")

    with pytest.raises(DataRejected, match="invalid_historical_rows"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, broken_archive(), source="fixture")


def test_historical_feed_generator_success_is_accepted():
    five, _ = feeds()
    from_generator = historical_rows(
        "SOLUSDT", FIVE_MINUTES_MS, (row for row in five), source="fixture"
    )
    from_list = historical_rows("SOLUSDT", FIVE_MINUTES_MS, five, source="fixture")
    assert from_generator == from_list


@pytest.mark.parametrize("failure", [TypeError, ValueError, RuntimeError, OSError, EOFError, OverflowError])
def test_historical_feed_iterator_initialization_failure_is_rejected(failure):
    class BrokenArchive:
        def __iter__(self):
            raise failure("archive unavailable before first row")

    with pytest.raises(DataRejected, match="invalid_historical_rows"):
        historical_rows("SOLUSDT", FIVE_MINUTES_MS, BrokenArchive(), source="fixture")
