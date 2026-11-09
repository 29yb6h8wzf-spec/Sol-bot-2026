"""Real Binance USDT-M 5m candle fixture (historical replay, not a live trade).

Source: Binance read-only futures klines connector, SOLUSDT, 2026-11-09.
Entry is an illustrative paper decision at the last closed bar; NOT a strategy signal.
No exchange order is submitted.
"""
from decimal import Decimal

from research.paper_market_replay import replay


def test_real_sol_candles_paper_take_profit(tmp_path):
    payload = {
        "symbol": "SOLUSDT", "signal_uid": "sol-real-bars-20261109-demo",
        "side": "SHORT", "quantity": "0.8", "entry_mid": "86.0000",
        "stop": "86.3000", "target": "85.8000", "opened_at": 1794221100,
        "bars": [
            {"open_ms": 1794221100000, "close_ms": 1794221399999,
             "high": "86.0700", "low": "85.9200", "close": "85.9800",
             "confirmed_closed": True},
            {"open_ms": 1794221400000, "close_ms": 1794221699999,
             "high": "86.0100", "low": "85.9100", "close": "85.9700",
             "confirmed_closed": True},
            {"open_ms": 1794221700000, "close_ms": 1794221999999,
             "high": "86.0200", "low": "85.9100", "close": "85.9200",
             "confirmed_closed": True},
            {"open_ms": 1794222000000, "close_ms": 1794222299999,
             "high": "85.9900", "low": "85.7800", "close": "85.8700",
             "confirmed_closed": True},
        ],
    }
    result = replay(payload, str(tmp_path / "real-candles.sqlite3"))
    assert result["bars_processed"] == 4
    assert result["trade"]["status"] == "EXECUTED_TP"
    assert Decimal(result["trade"]["net_pnl"]) > 0
    assert Decimal(result["trade"]["net_pnl"]) < Decimal(result["trade"]["gross_pnl"])
