"""Offline entrypoint tests: read-only and no outbound research publication."""

import pytest

import futures_engine.verified_strategy_scan as scanner


class DummyExchange:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def candles(interval_ms, now_ms, count=120):
    last_ms = now_ms - interval_ms
    start_ms = last_ms - (count - 1) * interval_ms
    return [
        [start_ms + i * interval_ms, 100.0, 101.0, 99.0, 100.0, 10.0]
        for i in range(count)
    ]


def test_candle_conversion_uses_closed_bar_prices():
    bars = [[300000, 10.0, 12.0, 9.0, 11.0, 7.0]]
    assert scanner.to_strategy_candles(bars) == [
        {"time": 300000, "high": 12.0, "low": 9.0,
         "close": 11.0, "volume": 7.0}
    ]


def test_evaluate_rejects_synthetic_strategy_without_publishing(monkeypatch):
    now_ms = 1_800_000_000_000
    connections = []

    def loader(symbol, timeframe):
        assert symbol == "BTC/USDT:USDT"
        interval = {"5m": 300000, "4h": 14400000}[timeframe]
        exchange = DummyExchange()
        connections.append(exchange)
        return exchange, {}, candles(interval, now_ms)

    def forbidden(*args, **kwargs):
        raise AssertionError("evaluate must not record or publish")

    monkeypatch.setattr(scanner, "candidates", lambda five, four: (
        [{"strategy": "E2E_SYNTHETIC_TEST", "direction": "LONG", "score": 85}],
        {},
    ))
    monkeypatch.setattr(scanner, "stage", forbidden)
    monkeypatch.setattr(scanner, "record", forbidden)

    result = scanner.evaluate("BTC/USDT:USDT", loader=loader, now_ms=now_ms)
    assert result["status"] == "RESEARCH_ONLY"
    assert result["candidates_85_plus"] == []
    assert len(result["rejected_candidates"]) == 1
    assert "unknown strategy" in result["rejected_candidates"][0]["reason"]
    assert result["orders_sent"] is False
    assert result["sqs_sent"] is False
    assert len(connections) == 2
    assert all(exchange.closed for exchange in connections)


def test_evaluate_closes_exchanges_on_invalid_4h_candles(monkeypatch):
    now_ms = 1_800_000_000_000
    connections = []

    def loader(symbol, timeframe):
        interval = {"5m": 300000, "4h": 14400000}[timeframe]
        bars = candles(interval, now_ms)
        if timeframe == "4h":
            bars[-2][0] += 1
        exchange = DummyExchange()
        connections.append(exchange)
        return exchange, {}, bars

    monkeypatch.setattr(scanner, "candidates", lambda five, four: (
        pytest.fail("invalid candles must not reach strategy logic"), {}
    ))
    with pytest.raises(ValueError, match="misaligned|noncontiguous"):
        scanner.evaluate("SOL/USDT:USDT", loader=loader, now_ms=now_ms)
    assert len(connections) == 2
    assert all(exchange.closed for exchange in connections)
