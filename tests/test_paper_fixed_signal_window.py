"""The Paper scanner uses identical indicator history at candle boundaries."""
import io
import json
from contextlib import redirect_stdout

import pytest
from futures_engine import __main__ as scanner
from futures_engine.paper import PaperLedger


class FakeExchange:
    def close(self):
        pass


@pytest.mark.parametrize("received_bars", [239, 240])
def test_scanner_uses_latest_239_closed_candles(tmp_path, monkeypatch, received_bars):
    bars = [
        [i * 900000, 100, 101, 99, 100, 10]
        for i in range(received_bars)
    ]
    used = []
    ledger = tmp_path / "paper.json"
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("FUTURES_SYMBOL", "SOL/USDT:USDT")
    monkeypatch.setenv("PAPER_LEDGER", str(ledger))
    monkeypatch.setenv("PAPER_START_EQUITY", "37.50")
    monkeypatch.setattr(
        scanner, "closed_futures_bars",
        lambda symbol, timeframe: (FakeExchange(), {}, bars))
    def record_window(closed):
        used.append([row[0] for row in closed])
        return None
    monkeypatch.setattr(scanner, "crossover_signal", record_window)
    output = io.StringIO()
    with redirect_stdout(output):
        scanner.main()
    response = json.loads(output.getvalue())
    assert len(used) == 1
    assert len(used[0]) == 239
    assert used[0][0] == bars[-239][0]
    assert used[0][-1] == bars[-1][0]
    assert response["signal"] is None and response["entry"] is None
    assert PaperLedger(ledger).state["history"] == []
