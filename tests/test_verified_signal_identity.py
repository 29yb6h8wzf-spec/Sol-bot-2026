import pytest
from verified_signal_identity import verified_event_key


def signal(**patch):
    return dict(signal_id="a", source="verified_85_score_engine",
                symbol="BTC/USDT:USDT", strategy="EMA_ADX",
                direction="long", closed_5m_candle_ms=300000,
                score=89, verification={"market": "verified"}, **patch)


def test_different_telegram_ids_same_economic_event():
    a = signal()
    b = {**a, "signal_id": "b", "score": 95}
    assert verified_event_key(a) == verified_event_key(b)


@pytest.mark.parametrize("change", [
    {"symbol": "ETH/USDT:USDT"}, {"direction": "short"},
    {"strategy": "BREAKOUT"}, {"closed_5m_candle_ms": 600000}
])
def test_distinct_economic_events_not_collapsed(change):
    assert verified_event_key(signal()) != verified_event_key({**signal(), **change})


@pytest.mark.parametrize("change", [
    {"source": "telegram"}, {"score": 84}, {"verification": {}},
    {"closed_5m_candle_ms": 300001}, {"strategy": ""},
])
def test_untrusted_or_invalid_verification_rejected(change):
    with pytest.raises(ValueError):
        verified_event_key({**signal(), **change})
