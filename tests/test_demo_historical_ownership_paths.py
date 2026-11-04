"""Offline regression for confirmed vs mismatched historical order ownership."""
import demo_historical_attribution_report as module
from test_demo_historical_attribution_report import Demo, DAY, SYMBOL, fill


def test_matching_order_is_attributed(monkeypatch, tmp_path):
    trusted = {(SYMBOL, "11"): {"client_order_id": "SPDEMO-confirmed"}}
    monkeypatch.setattr(module, "registry_orders", lambda path: (trusted, True))
    result = module.report(Demo([fill()], client="SPDEMO-confirmed"), DAY,
                           registry_path=tmp_path / "unused")
    assert result["total_fills"] == 1
    assert result["unattributed_fills"] == 0
    assert result["orders"][0]["ownership"] == "SIGNALPILOT_CONFIRMED"
    assert result["execution_authorized"] is False


def test_mismatched_order_is_not_attributed(monkeypatch, tmp_path):
    trusted = {(SYMBOL, "11"): {"client_order_id": "SPDEMO-confirmed"}}
    monkeypatch.setattr(module, "registry_orders", lambda path: (trusted, True))
    result = module.report(Demo([fill()], client="OTHER"), DAY,
                           registry_path=tmp_path / "unused")
    assert result["unattributed_fills"] == 1
    assert result["orders"][0]["ownership"] == "UNATTRIBUTED"
    assert result["execution_authorized"] is False
