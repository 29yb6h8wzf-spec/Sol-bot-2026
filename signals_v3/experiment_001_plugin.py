"""SignalPilot V3 adapter for Experiment 001 v3 (research only, no orders).

Run with EXP001_ROOT (verified ZIP directory), EXP001_MANIFEST (quality
exclusion JSON), EXP001_MONTH (YYYY-MM), EXP001_STRIDE (default 12).
The experiment's exporter is a separate, untrusted research dependency.
"""
import bisect
import os
from pathlib import Path
from experiment_001.export_signalpilot import Hooks
from signals_v2.contracts import DataRejected
from signals_v2.replay import replay
from signals_v2.guarded_replay import guarded_replay
from signals_v2.backtest_exclusion_gate import eligible, load_manifest
from signals_v3.router import candidates
from signals_v3.pilot_replay import replay_hypothesis, candles, iter_rows

SYMBOLS = ("SOLUSDT", "XRPUSDT")
STRIDE = int(os.environ.get("EXP001_STRIDE", "12"))
if STRIDE < 1:
    raise ValueError("invalid_experiment_stride")

def hooks():
    return Hooks(eligible=eligible, candidates=candidates,
                 replay_hypothesis=replay_hypothesis,
                 guarded_replay=guarded_replay, replay_core=replay,
                 rejected_exceptions=(DataRejected, ValueError, IndexError),
                 strategy_of=lambda p: p.specialist)

def load(symbol):
    if symbol not in SYMBOLS:
        raise ValueError("unsupported_experiment_symbol")
    root = Path(os.environ["EXP001_ROOT"])
    manifest = os.environ["EXP001_MANIFEST"]
    month = os.environ.get("EXP001_MONTH", "2026-09")
    if len(month) != 7 or month[4] != "-" or not (month[:4] + month[5:]).isdigit():
        raise ValueError("invalid_experiment_month")
    five = candles(root / f"{symbol}-5m-{month}.zip", 300000)
    one = candles(root / f"{symbol}-1m-{month}.zip", 60000)
    one_times = [bar.available_at_ms for bar in one]
    funding = [(t, float(row[2])) for t, row in iter_rows(root / f"{symbol}-fundingRate-{month}.zip")]
    intervals = load_manifest(manifest)
    return five, one, one_times, funding, intervals
