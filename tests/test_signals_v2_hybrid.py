"""Synthetic, offline research-only tests for hybrid engine and features."""
from dataclasses import replace
import pytest
from signals_v2.contracts import Candle, DataRejected
from signals_v2.features import features, ema
from signals_v2.hybrid import candidates
from test_signals_v2_regime import snapshot


def test_flat_regime_never_proposes_orders():
    assert candidates(snapshot()) == ()


def test_hypotheses_are_never_execution_authorized():
    for case in (snapshot(), snapshot(breakout=True), snapshot(high_volatility=True)):
        for proposal in candidates(case):
            assert proposal.research_only is True
            assert proposal.execution_authorized is False
            assert proposal.calibrated_probability is None
            assert proposal.quality_score is None
            assert proposal.stop_reference > 0
            assert proposal.target_reference > 0
            assert proposal.valid_until_ms > proposal.decision_ms
            if proposal.direction == "LONG":
                assert proposal.stop_reference < proposal.entry_reference < proposal.target_reference
            else:
                assert proposal.target_reference < proposal.entry_reference < proposal.stop_reference


def test_features_are_causal_and_have_closed_bar_timestamp():
    s = snapshot()
    f = features(s.five_minute, decision_ms=s.decision_ms)
    assert f.atr14 > 0
    assert f.relative_volume == pytest.approx(1)
    assert f.available_at_ms == s.five_minute[-1].open_ms + 300_000
    assert features(s.five_minute, decision_ms=s.decision_ms) == f


def test_features_reject_future_bar():
    s = snapshot()
    future = replace(s.five_minute[-1], available_at_ms=s.decision_ms + 1000)
    with pytest.raises(DataRejected):
        features(s.five_minute[:-1] + (future,), decision_ms=s.decision_ms)


def test_features_reject_missing_bar():
    s = snapshot()
    with pytest.raises(DataRejected, match="missing_or_duplicate"):
        features(s.five_minute[:40] + s.five_minute[41:], decision_ms=s.decision_ms)


def test_ema_rejects_short_input():
    with pytest.raises(DataRejected):
        ema((1.0, 2.0), 9)
