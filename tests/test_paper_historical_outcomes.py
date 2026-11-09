"""Historical 85+ outcomes are conservative, fee-adjusted, and not forward proof."""
import json
from decimal import Decimal
from pathlib import Path

from research.paper_historical_outcomes import audit_historical_outcomes

FIXTURES = Path(__file__).parent / "fixtures"


def test_real_sol_xrp_historical_candidates_have_honest_outcome_labels():
    payload = json.loads((
        FIXTURES / "forward_connector_snapshot_20261109_2023utc.json"
    ).read_text(encoding="utf-8"))
    expected = {"XRP/USDT:USDT": 5, "SOL/USDT:USDT": 2}
    for item in payload["items"]:
        result = audit_historical_outcomes(
            item["five"], item["four"], symbol=item["symbol"],
            asof_ms=payload["captured_at_ms"],
        )
        assert result["status"] == "HISTORICAL_IN_SAMPLE_PAPER_AUDIT"
        assert result["raw_candidates_85_plus"] == expected[item["symbol"]]
        assert result["orders_sent"] is False
        assert result["out_of_sample"] is False
        assert result["profitability_validated"] is False
        assert result["funding_included"] is False
        assert sum(result["statuses"].values()) == expected[item["symbol"]]
        for trade in result["outcomes"]:
            assert trade["orders_sent"] is False
            if "net_pnl_usd" in trade:
                assert trade["status"] in ("EXECUTED_SL", "EXECUTED_TP", "EXPIRED")
                assert Decimal(trade["estimated_risk_usd"]) <= Decimal("1.50")
                assert Decimal(trade["net_pnl_usd"]).is_finite()
        print(json.dumps(result, sort_keys=True))


def test_verified_xrp_history_historical_audit_has_at_least_one_signal():
    payload = json.loads((
        FIXTURES / "xrpusdt_verified_20261109.json"
    ).read_text(encoding="utf-8"))
    result = audit_historical_outcomes(
        payload["five"], payload["four"], symbol=payload["symbol"],
        asof_ms=payload["asof_ms"],
    )
    assert result["raw_candidates_85_plus"] >= 1
    assert result["orders_sent"] is False
