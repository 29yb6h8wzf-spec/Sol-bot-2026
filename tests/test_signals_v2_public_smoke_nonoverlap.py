"""Smoke runner regression: non-overlap is distinct from raw proposals.

Synthetic fixtures are not evidence of trading performance.
"""
from unittest.mock import patch
from types import SimpleNamespace

from signals_v2.hybrid import Hypothesis
from signals_v2.public_smoke import run_symbol


BASE = 1_800_000_000_000


def _rows(count, step):
    return [[BASE + i * step, "100", "101", "99", "100", "10"]
            for i in range(count)]


def test_smoke_reports_raw_and_nonoverlap_separately():
    five = _rows(140, 300_000)
    one = _rows(700, 60_000)

    def fake_fetch(symbol, interval, limit=1000):
        return five if interval == "5m" else one

    def fake_candidates(snapshot):
        return (Hypothesis("signals.v2.research.1", snapshot.symbol, "LONG",
                           "trend_continuation", "TREND", snapshot.decision_ms,
                           100.0, 99.0, 102.0, snapshot.decision_ms + 600_000),)

    with patch("signals_v2.public_smoke.fetch", side_effect=fake_fetch), \
         patch("signals_v2.public_smoke.candidates", side_effect=fake_candidates), \
         patch("signals_v2.public_smoke.replay",
               return_value=SimpleNamespace(net_r=-1.0, exit_reason="STOP")):
        result = run_symbol("SOLUSDT")
    assert result["proposals"] > result["nonoverlap_replayed"] >= 1
    assert result["replayed"] == result["proposals"]
    assert result["net_r_descriptive"] == -result["replayed"]
    assert result["nonoverlap_net_r"] == -result["nonoverlap_replayed"]
    assert sum(result["nonoverlap_exit_reasons"].values()) == result["nonoverlap_replayed"]
    assert result["status"] == "DIAGNOSTIC_ONLY_NOT_OOS"
