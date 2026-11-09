"""Deterministic replay acceptance test; synthetic candles, not live market proof."""
from research.paper_market_replay import replay


def test_paper_replay_reports_net_pnl_and_restart(tmp_path):
    payload = {
        "symbol": "SOLUSDT", "signal_uid": "paper-e2e-1", "side": "LONG",
        "quantity": "1", "entry_mid": "100", "stop": "98", "target": "104",
        "opened_at": 1700000000,
        "bars": [{
            "open_ms": 1700000000000, "close_ms": 1700000299999,
            "high": "105", "low": "99", "close": "104",
            "confirmed_closed": True,
        }],
    }
    db = str(tmp_path / "replay.sqlite3")
    first = replay(payload, db)
    second = replay(payload, db)
    assert first == second
    assert first["bars_processed"] == 1
    assert first["trade"]["status"] == "EXECUTED_TP"
    assert first["trade"]["net_pnl"] is not None
    assert float(first["trade"]["net_pnl"]) < float(first["trade"]["gross_pnl"])
