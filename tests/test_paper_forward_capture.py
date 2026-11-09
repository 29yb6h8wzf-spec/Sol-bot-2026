"""Read-only forward capture is idempotent and never places a trade."""
import json
from pathlib import Path

import pytest

from research.paper_forward_capture import capture_scan
from research.paper_forward_followup import replay_captured_bundle

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
