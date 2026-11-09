"""Independently evaluate read-only market data saved before the next bar closed.

The data was captured via an authorized public-data connector; no exchange
network access or order API is used by this test.
"""
import json
from pathlib import Path

from futures_engine.verified_strategy_scan import evaluate, to_strategy_candles
from research.paper_independent_verifier import verify_saved_scan
from research.paper_forward_once import run_from_connector_snapshot

SNAPSHOT = Path(__file__).parent / "fixtures" / "forward_connector_snapshot_20261109_2023utc.json"


class _Exchange:
    def close(self):
        pass


def _make_loader(symbol, five, four):
    def loader(requested_symbol, timeframe):
        assert requested_symbol == symbol
        return _Exchange(), {}, five if timeframe == "5m" else four

    return loader


def test_forward_connector_snapshot_closed_and_independently_scannable():
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert len(payload["items"]) == 2
    capture = payload["captured_at_ms"]
    seen = set()
    for item in payload["items"]:
        symbol = item["symbol"]
        assert symbol not in seen
        seen.add(symbol)
        five, four = item["five"], item["four"]
        assert len(five) == len(four) == 240
        assert all(row[0] + 300000 <= capture for row in five)
        assert all(row[0] + 14400000 <= capture for row in four)
        assert five[-1][0] + 300000 <= capture < five[-1][0] + 600000

        scan = evaluate(
            symbol, loader=_make_loader(symbol, five, four), now_ms=capture,
        )
        assert scan["status"] == "RESEARCH_ONLY"
        assert scan["orders_sent"] is False
        for index in range(len(scan["candidates_85_plus"])):
            verified = verify_saved_scan(
                scan, to_strategy_candles(five), to_strategy_candles(four),
                candidate_index=index,
            )
            assert verified["execution_authorized"] is False
        print(json.dumps({
            "symbol": symbol, "capture_ms": capture,
            "signal_candle_ms": scan["closed_5m_candle_ms"],
            "eligible_candidates": scan["candidates_85_plus"],
            "rejected_candidates": scan["rejected_candidates"],
            "orders_sent": False,
        }, sort_keys=True))
    assert seen == {"SOL/USDT:USDT", "XRP/USDT:USDT"}


def test_authorized_connector_snapshot_ingests_both_symbols_offline(tmp_path):
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    snapshots = tmp_path / "snapshots"
    db = str(tmp_path / "paper.db")
    first = run_from_connector_snapshot(
        payload, snapshot_dir=snapshots, database_path=db,
    )
    assert first["status"] == "RESEARCH_PAPER_ONLY"
    assert first["orders_sent"] is False
    assert len(first["captures"]) == 2
    assert all(item["status"] == "RECORDED" for item in first["captures"])
    assert all(item["candidate_count"] == 0 for item in first["captures"])
    again = run_from_connector_snapshot(
        payload, snapshot_dir=snapshots, database_path=db,
    )
    assert all(item["status"] == "ALREADY_RECORDED" for item in again["captures"])
    assert len(list(snapshots.glob("*.json"))) == 2
    assert not (tmp_path / "paper.db").exists()
