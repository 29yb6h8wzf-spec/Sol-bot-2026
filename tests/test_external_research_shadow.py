from external_research_shadow import compare
import pytest


def test_algovault_hold_is_neutral_and_never_authorizes():
    result = compare({"symbol": "BTCUSDT", "direction": "long"},
                     {"coin": "BTC", "call": "HOLD", "confidence": 6,
                      "regime": "TRENDING_UP"})
    assert result["providers"]["algovault"]["agreement"] == "neutral"
    assert result["execution_authorized"] is False
    assert result["orders_sent"] is False


def test_disagreement_does_not_change_risk_gate():
    result = compare({"symbol": "SOLUSDT", "direction": "short"},
                     {"coin": "SOL", "call": "BUY", "confidence": 90},
                     {"run_id": "offline-run-123"})
    assert result["providers"]["algovault"]["agreement"] == "disagree"
    assert result["providers"]["premiss"]["status"] == "historical_context_only"
    assert result["execution_authorized"] is False


def test_wrong_coin_is_ignored():
    result = compare({"symbol": "ETHUSDT", "direction": "long"},
                     {"coin": "BTC", "call": "BUY"})
    assert result["provider_count"] == 0


@pytest.mark.parametrize("signal", [{}, {"symbol": "DOGEUSDT", "direction": "long"},
                                    {"symbol": "BTCUSDT", "direction": "BUY"}])
def test_invalid_signal_fails_closed(signal):
    with pytest.raises(ValueError):
        compare(signal)
