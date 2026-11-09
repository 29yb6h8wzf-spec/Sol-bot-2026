"""Read-only forward capture is idempotent and never places a trade."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from research.paper_forward_capture import capture_scan
from research.paper_forward_followup import replay_captured_bundle
from research.paper_forward_once import process_pending, run_once

FIXTURE = Path(__file__).parent / "fixtures" / "xrpusdt_verified_20261109.json"


class _Exchange:
    def close(self):
        pass


def _inputs():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def loader(symbol, timeframe):
        assert symbol == data["symbol"]
        return _Exchange(), {}, data["five"] if timeframe == "5m" else data["four"]

    return data, loader


def test_forward_capture_creates_one_immutable_snapshot(tmp_path):
    data, loader = _inputs()
    first = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=data["asof_ms"],
    )
    again = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=data["asof_ms"],
    )
    assert first["status"] == "RECORDED"
    assert again["status"] == "ALREADY_RECORDED"
    assert first["candidate_count"] >= 1
    assert first["orders_sent"] is False
    assert first["paper_trade_opened"] is False
    assert len(list(tmp_path.glob("*.json"))) == 1
    saved = json.loads(Path(first["snapshot_path"]).read_text(encoding="utf-8"))
    assert saved["scan"]["orders_sent"] is False
    assert saved["scan"]["candidates_85_plus"][0]["verification"]["execution_authorized"] is False
    assert saved["five"] == data["five"]
    assert saved["four"] == data["four"]


def test_forward_capture_refuses_conflicting_existing_snapshot(tmp_path):
    data, loader = _inputs()
    first = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=data["asof_ms"],
    )
    Path(first["snapshot_path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting existing"):
        capture_scan(
            data["symbol"], output_dir=tmp_path, loader=loader,
            now_ms=data["asof_ms"],
        )


def test_captured_bundle_replays_verified_real_xrp_without_orders(tmp_path):
    data, loader = _inputs()
    saved = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=data["asof_ms"],
    )
    bundle = json.loads(Path(saved["snapshot_path"]).read_text(encoding="utf-8"))
    result = replay_captured_bundle(
        bundle, data["future"], database_path=str(tmp_path / "paper.db"),
        observed_at_ms=data["future"][-1][0] + 300000,
    )
    assert result["status"] == "OFFLINE_PAPER_REPLAY"
    assert result["orders_sent"] is False
    assert result["result"]["trade"]["status"] == "EXECUTED_SL"
    assert result["result"]["paper_plan"]["paper_only"] is True


def test_followup_rejects_future_unclosed_bar(tmp_path):
    data, loader = _inputs()
    saved = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=data["asof_ms"],
    )
    bundle = json.loads(Path(saved["snapshot_path"]).read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="not closed"):
        replay_captured_bundle(
            bundle, data["future"], database_path=str(tmp_path / "paper.db"),
            observed_at_ms=data["future"][0][0] + 1,
        )


def test_followup_rejects_tampered_saved_scan(tmp_path):
    data, loader = _inputs()
    saved = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=data["asof_ms"],
    )
    bundle = json.loads(Path(saved["snapshot_path"]).read_text(encoding="utf-8"))
    bundle["scan"]["candidates_85_plus"][0]["score"] = 99
    with pytest.raises(ValueError):
        replay_captured_bundle(
            bundle, data["future"], database_path=str(tmp_path / "paper.db"),
            observed_at_ms=data["future"][-1][0] + 300000,
        )


def test_one_shot_capture_waits_then_replays_real_xrp_forward_bundle(tmp_path):
    data, loader = _inputs()
    snapshots = tmp_path / "snapshots"
    db = str(tmp_path / "paper.db")
    first = run_once(
        snapshot_dir=snapshots, database_path=db,
        symbols=(data["symbol"],), loader=loader,
        now_ms=data["asof_ms"],
    )
    assert first["status"] == "RESEARCH_PAPER_ONLY"
    assert first["orders_sent"] is False
    assert first["captures"][0]["status"] == "RECORDED"
    assert first["followups"][0]["status"] == "WAITING_NEXT_BAR"

    def later_loader(symbol, timeframe):
        assert symbol == data["symbol"]
        if timeframe != "5m":
            raise AssertionError("followup should only fetch 5m")
        return _Exchange(), {}, data["five"] + data["future"]

    now = data["future"][-1][0] + 300000
    followups = process_pending(
        snapshot_dir=snapshots, database_path=db,
        loader=later_loader, now_ms=now,
    )
    assert len(followups) == 1
    assert followups[0]["status"] == "EXECUTED_SL"
    assert followups[0]["paper_only"] is True
    assert float(followups[0]["net_pnl"]) >= -1.50
    assert process_pending(
        snapshot_dir=snapshots, database_path=db,
        loader=later_loader, now_ms=now,
    ) == followups


def test_capture_rejects_retroactive_signal_snapshot(tmp_path):
    data, loader = _inputs()
    with pytest.raises(ValueError, match="unfinished candle|stale candles|forward capture"):
        capture_scan(
            data["symbol"], output_dir=tmp_path, loader=loader,
            now_ms=data["asof_ms"] + 600000,
        )
    assert not list(tmp_path.glob("*.json"))


def test_followup_blocks_tampered_capture_time(tmp_path):
    data, loader = _inputs()
    first = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=data["asof_ms"],
    )
    path = Path(first["snapshot_path"])
    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["captured_at_ms"] = data["asof_ms"] + 600000
    path.write_text(json.dumps(bundle), encoding="utf-8")
    outcomes = process_pending(
        snapshot_dir=tmp_path, database_path=str(tmp_path / "paper.db"),
        loader=loader, now_ms=data["asof_ms"] + 900000,
    )
    assert outcomes[0]["status"] == "BLOCKED"
    assert "forward capture timestamp" in outcomes[0]["reason"]


def test_delayed_capture_never_fills_at_already_open_candle(tmp_path):
    data, loader = _inputs()
    capture_ms = data["asof_ms"] + 10000
    saved = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=capture_ms,
    )
    bundle = json.loads(Path(saved["snapshot_path"]).read_text(encoding="utf-8"))
    with patch("research.paper_forward_followup.replay_saved_scan",
               return_value={"trade": {"status": "OPEN"}}) as replay:
        replay_captured_bundle(
            bundle, data["future"], database_path=str(tmp_path / "paper.db"),
            observed_at_ms=data["future"][-1][0] + 300000,
        )
    assert replay.call_args.kwargs["entry_open_ms"] == data["asof_ms"] + 300000


def test_delayed_capture_waits_for_second_future_candle(tmp_path):
    data, loader = _inputs()
    saved = capture_scan(
        data["symbol"], output_dir=tmp_path, loader=loader,
        now_ms=data["asof_ms"] + 10000,
    )
    assert saved["status"] == "RECORDED"
    observed = data["asof_ms"] + 300000
    outcomes = process_pending(
        snapshot_dir=tmp_path, database_path=str(tmp_path / "paper.db"),
        loader=loader, now_ms=observed,
    )
    assert outcomes[0]["status"] == "WAITING_NEXT_BAR"


def test_restricted_public_market_feed_is_explicitly_blocked(tmp_path):
    def restricted_loader(_symbol, _timeframe):
        raise RuntimeError("public Binance 451 restricted location")

    result = run_once(
        snapshot_dir=tmp_path / "snapshots",
        database_path=str(tmp_path / "paper.db"),
        loader=restricted_loader,
        now_ms=1794255800706,
    )
    assert result["status"] == "BLOCKED_MARKET_DATA"
    assert len(result["captures"]) == 2
    assert all(item["status"] == "BLOCKED" for item in result["captures"])
    assert result["followups"] == []
    assert result["orders_sent"] is False
    assert not (tmp_path / "paper.db").exists()
