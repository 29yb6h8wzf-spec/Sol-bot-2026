"""Offline integration regression: no private Binance orders are sent."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

import signalpilot_quant_mr as bot


def exchange():
    ex = MagicMock()
    ex.fapiPrivateGetPositionSideDual.return_value = {"dualSidePosition": False}
    ex.fapiPrivatePostLeverage.return_value = {"leverage": 3}
    ex.fapiPublicGetPremiumIndex.return_value = {"markPrice": "100", "time": 1000}
    ex.fetch_time.return_value = 1000
    ex.fetch_balance.return_value = {"info": {"assets": [{
        "asset": "USDT", "walletBalance": "150", "availableBalance": "145",
        "marginBalance": "150",
    }]}}
    ex.market.return_value = {"info": {"filters": [
        {"filterType": "LOT_SIZE", "stepSize": "0.01", "minQty": "0.01",
         "maxQty": "80000"},
        {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.01",
         "minQty": "0.01", "maxQty": "80000"},
        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
        {"filterType": "MIN_NOTIONAL", "notional": "5"},
    ]}}
    return ex


def test_latched_daily_loss_persists_after_wallet_recovery_and_restart():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "risk.sqlite3"
        state = bot.State(path)
        state.check_daily_limit(Decimal(150), Decimal(150))
        with pytest.raises(bot.SafetyError, match="drawdown"):
            state.check_daily_limit(Decimal(145), Decimal(142))
        state.db.close()
        restarted = bot.State(path)
        with pytest.raises(bot.SafetyError, match="latched"):
            restarted.check_daily_limit(Decimal(150), Decimal(150))
        restarted.db.close()


def test_mark_price_requires_timestamp_and_fresh_exchange_clock():
    ex = exchange()
    ex.fapiPublicGetPremiumIndex.return_value = {"markPrice": "100"}
    with pytest.raises(bot.SafetyError, match="timestamp"):
        bot.mark_price(ex, "SOL/USDT:USDT")
    ex.fapiPublicGetPremiumIndex.return_value = {"markPrice": "100", "time": 1000}
    ex.fetch_time.return_value = 30000
    with pytest.raises(bot.SafetyError, match="Stale"):
        bot.mark_price(ex, "SOL/USDT:USDT")


def test_quantity_uses_slippage_buffer_and_never_exceeds_5pct_margin():
    ex = exchange()
    qty = bot.entry_quantity(ex, "SOL/USDT:USDT",
                             Decimal(150), Decimal(145), Decimal(100))
    assert qty == Decimal("0.22")
    assert qty * Decimal(100) / 3 <= Decimal("7.5")
    with pytest.raises(bot.SafetyError, match="minimum"):
        bot.entry_quantity(ex, "SOL/USDT:USDT",
                           Decimal(10), Decimal(10), Decimal(100))


def test_pending_entry_restart_flattens_but_never_clears_ambiguous_marker(monkeypatch):
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)
    ex = exchange()
    positions = [True]
    ex.fetch_positions.side_effect = lambda: ([{"info": {
        "symbol": "SOLUSDT", "positionAmt": "0.22",
        "entryPrice": "100", "positionSide": "BOTH",
    }}] if positions else [])
    ex.fapiPrivateGetOpenAlgoOrders.return_value = []

    def reduce_only(*args):
        assert args[5]["reduceOnly"] is True
        positions.clear()
        return {"id": "flatten"}

    ex.create_order.side_effect = reduce_only
    with TemporaryDirectory() as directory:
        state = bot.State(Path(directory) / "pending.sqlite3")
        state.set_managed("SOL/USDT:USDT", "PENDING", "QMR_SOL_EN")
        with pytest.raises(bot.SafetyError, match="manual reconciliation"):
            bot.reconcile(ex, state, bot.all_positions(ex))
        assert not positions
        assert state.managed("SOL/USDT:USDT")["status"] == "PENDING"
        state.db.close()


@pytest.mark.parametrize("tamper", [
    {"side": "BUY"},
    {"triggerPrice": "NaN"},
    {"triggerPrice": "0"},
    {"workingType": "CONTRACT_PRICE"},
])
def test_wrong_protection_is_flattened_and_sibling_removed(monkeypatch, tamper):
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)
    ex = exchange()
    positions = [True]
    algos = [
        {"algoId": "11", "clientAlgoId": "QMR_SOL_SL", "symbol": "SOLUSDT",
         "type": "STOP_MARKET", "side": "SELL", "triggerPrice": "98.50",
         "closePosition": "true", "workingType": "MARK_PRICE", "positionSide": "BOTH"},
        {"algoId": "12", "clientAlgoId": "QMR_SOL_TP", "symbol": "SOLUSDT",
         "type": "TAKE_PROFIT_MARKET", "side": "SELL", "triggerPrice": "103.00",
         "closePosition": "true", "workingType": "MARK_PRICE", "positionSide": "BOTH"},
    ]
    algos[0].update(tamper)
    ex.fetch_positions.side_effect = lambda: ([{"info": {
        "symbol": "SOLUSDT", "positionAmt": "0.22",
        "entryPrice": "100", "positionSide": "BOTH",
    }}] if positions else [])
    ex.fapiPrivateGetOpenAlgoOrders.side_effect = lambda req: list(algos)
    ex.fapiPrivateDeleteAlgoOrder.side_effect = lambda req: algos.__setitem__(
        slice(None), [a for a in algos if a["algoId"] != str(req["algoId"])]
    )

    def reduce_only(*args):
        assert args[5]["reduceOnly"] is True
        positions.clear()
        return {"id": "flatten"}

    ex.create_order.side_effect = reduce_only
    with TemporaryDirectory() as directory:
        state = bot.State(Path(directory) / "protection.sqlite3")
        state.set_managed("SOL/USDT:USDT", "PROTECTED", "entry", "11", "12")
        with pytest.raises(bot.SafetyError, match="Protective orders"):
            bot.reconcile(ex, state, bot.all_positions(ex))
        assert not positions and not algos
        assert state.managed("SOL/USDT:USDT") is None
        state.db.close()


def test_full_market_entry_and_two_algos_then_sibling_cleanup(monkeypatch):
    monkeypatch.setattr(bot, "LIVE", True)
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)
    ex = exchange()
    positions = []
    algos = []

    def fetch_positions():
        return [{"info": {"symbol": "SOLUSDT", "positionAmt": "0.22",
                          "entryPrice": "100", "positionSide": "BOTH"}}] if positions else []

    def order(*args):
        positions.append(True)
        return {"id": "simulated-fill"}

    def place_algo(payload):
        result = dict(payload)
        result["algoId"] = str(100 + len(algos))
        algos.append(result)
        return {"algoId": result["algoId"]}

    ex.fetch_positions.side_effect = fetch_positions
    ex.create_order.side_effect = order
    ex.fapiPrivateGetOpenAlgoOrders.side_effect = lambda req: list(algos)
    ex.fapiPrivatePostAlgoOrder.side_effect = place_algo
    ex.fapiPrivateDeleteAlgoOrder.side_effect = lambda req: algos.__setitem__(
        slice(None), [a for a in algos if a["algoId"] != str(req["algoId"])]
    )
    with TemporaryDirectory() as directory:
        state = bot.State(Path(directory) / "entry.sqlite3")
        bot.execute_signal(ex, state, "SOL/USDT:USDT", "LONG",
                           1234500000, Decimal(100))
        assert state.managed("SOL/USDT:USDT")["status"] == "PROTECTED"
        assert {a["type"] for a in algos} == {"STOP_MARKET", "TAKE_PROFIT_MARKET"}
        assert all(a["closePosition"] == "true" and a["workingType"] == "MARK_PRICE"
                   for a in algos)
        positions.clear()
        algos.pop(0)
        bot.reconcile(ex, state, {})
        assert not algos
        assert state.managed("SOL/USDT:USDT") is None
        state.db.close()


def test_algo_service_failure_flattens_and_blocks_retry(monkeypatch):
    monkeypatch.setattr(bot, "LIVE", True)
    monkeypatch.setattr(bot.time, "sleep", lambda _: None)
    ex = exchange()
    positions = []
    algos = []

    def fetch_positions():
        return [{"info": {"symbol": "SOLUSDT", "positionAmt": "0.22",
                          "entryPrice": "100", "positionSide": "BOTH"}}] if positions else []

    def order(*args):
        if args[5].get("reduceOnly"):
            positions.clear()
        else:
            positions.append(True)
        return {"id": "mock-order"}

    def place_algo(payload):
        if payload["type"] == "TAKE_PROFIT_MARKET":
            raise RuntimeError("simulated exchange timeout")
        algos.append({**payload, "algoId": "77"})
        return {"algoId": "77"}

    ex.fetch_positions.side_effect = fetch_positions
    ex.create_order.side_effect = order
    ex.fapiPrivateGetOpenAlgoOrders.side_effect = lambda req: list(algos)
    ex.fapiPrivatePostAlgoOrder.side_effect = place_algo
    ex.fapiPrivateDeleteAlgoOrder.side_effect = lambda req: algos.clear()
    with TemporaryDirectory() as directory:
        state = bot.State(Path(directory) / "failure.sqlite3")
        with pytest.raises(RuntimeError, match="timeout"):
            bot.execute_signal(ex, state, "SOL/USDT:USDT", "LONG",
                               1234500000, Decimal(100))
        assert not positions and not algos
        assert state.managed("SOL/USDT:USDT")["status"] == "PENDING"
        state.db.close()
