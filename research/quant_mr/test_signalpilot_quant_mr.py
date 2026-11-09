"""Offline safety/indicator checks. Install ccxt to run against its real module."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import signalpilot_quant_mr as bot


def test_15m_signals_use_previous_20_closed_bars():
    ex = MagicMock()
    bars = []
    for i in range(20):
        price = 99 if i % 2 else 101
        bars.append([i * bot.INTERVAL_MS, price, price + 0.5, price - 0.5,
                     price, 10])
    bars.append([20 * bot.INTERVAL_MS, 100, 101, 99, 100, 16])
    ex.fetch_ohlcv.return_value = bars
    ex.fetch_time.return_value = 1000
    now_ms = 21 * bot.INTERVAL_MS + 2500
    ex.fapiPublicGetPremiumIndex.return_value = {"markPrice": "97", "time": 1000}
    result = bot.calculate_signal(ex, "SOL/USDT:USDT", now_ms)
    assert result[1] == "LONG"
    ex.fapiPublicGetPremiumIndex.return_value = {"markPrice": "103", "time": 1000}
    assert bot.calculate_signal(ex, "SOL/USDT:USDT", now_ms)[1] == "SHORT"
    bars[-1][-1] = 14
    assert bot.calculate_signal(ex, "SOL/USDT:USDT", now_ms)[1] is None
    assert bot.calculate_signal(ex, "SOL/USDT:USDT", now_ms + 15000) is None


def test_margin_quantity_and_price_rounding():
    ex = MagicMock()
    ex.market.return_value = {"info": {"filters": [
        {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.01", "maxQty": "80000"},
        {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.01", "minQty": "0.01", "maxQty": "80000"},
        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
        {"filterType": "MIN_NOTIONAL", "notional": "5"},
    ]}}
    qty = bot.entry_quantity(ex, "SOL/USDT:USDT", Decimal("150"),
                             Decimal("150"), Decimal("100"))
    assert qty == Decimal("0.22")
    assert qty * 100 <= Decimal("22.5")
    stop, take = bot.protection_prices(Decimal("100"), "LONG", Decimal("0.01"))
    assert stop == Decimal("98.50")
    assert take == Decimal("103.00")
    stop, take = bot.protection_prices(Decimal("100"), "SHORT", Decimal("0.01"))
    assert stop == Decimal("101.50")
    assert take == Decimal("97.00")


def test_conditional_close_all_uses_algo_service():
    ex = MagicMock()
    bot.algo_order(ex, "XRP/USDT:USDT", "LONG", "STOP_MARKET",
                   Decimal("1.01"), "QMR_XRP_SL")
    payload = ex.fapiPrivatePostAlgoOrder.call_args.args[0]
    assert payload["closePosition"] == "true"
    assert payload["workingType"] == "MARK_PRICE"
    assert payload["triggerPrice"] == "1.01"
    assert "quantity" not in payload and "reduceOnly" not in payload


def test_pending_state_does_not_allow_replay():
    with TemporaryDirectory() as directory:
        state = bot.State(Path(directory) / "test.sqlite3")
        assert state.mark_seen("SOL/USDT:USDT", 1234)
        assert not state.mark_seen("SOL/USDT:USDT", 1234)
        state.set_managed("SOL/USDT:USDT", "PENDING", "QMR_entry")
        ex = MagicMock()
        ex.fapiPrivateGetOpenAlgoOrders.return_value = []
        try:
            bot.reconcile(ex, state, {})
        except bot.SafetyError as exc:
            assert "pending MARKET" in str(exc)
        else:
            raise AssertionError("Pending market order was silently cleared")
        assert state.managed("SOL/USDT:USDT")["status"] == "PENDING"
        state.db.close()