"""Offline-only diagnostics; no keys, live prices, or trading."""
from decimal import Decimal as D
import io
import json
from contextlib import redirect_stdout

import pytest

from futures_engine import core
from futures_engine import paper_signal_filter_audit as diagnosis
from futures_engine import __main__ as scanner


def flat_bars(n=239):
    return [[i * 900000, "100", "101", "99", "100", "10"]
            for i in range(n)]


def test_flat_prices_have_no_ema_crossover_and_no_trade():
    report = diagnosis.explain_paper_signal(flat_bars())
    assert report["condition"] == "NO_EMA_CROSS"
    assert report["candidate"] is None
    assert report["rsi14"] == "50"
    assert report["ema50_now"] == report["ema200_now"]
    assert report["execution_authorized"] is False
    assert report["orders_sent"] is False


@pytest.mark.parametrize("before,now,momentum,reason,candidate", [
    ((90, 100), (101, 100), "54", "LONG_PASSED", "long"),
    ((90, 100), (101, 100), "55", "LONG_CROSS_RSI_NOT_BELOW_55", None),
    ((110, 100), (99, 100), "46", "SHORT_PASSED", "short"),
    ((110, 100), (99, 100), "45", "SHORT_CROSS_RSI_NOT_ABOVE_45", None),
    ((99, 100), (99, 100), "54", "NO_EMA_CROSS", None),
])
def test_filter_reasons_follow_strict_paper_rules(monkeypatch, before, now, momentum,
                                                   reason, candidate):
    def fake_ema(prices, length):
        fast, slow = before if len(prices) == 201 else now
        return D(fast if length == 50 else slow)
    monkeypatch.setattr(diagnosis, "ema", fake_ema)
    monkeypatch.setattr(diagnosis, "rsi", lambda prices: D(momentum))
    report = diagnosis.explain_paper_signal(flat_bars(202))
    assert report["condition"] == reason
    assert report["candidate"] == candidate


@pytest.mark.parametrize("trend", [-1, 0, 1])
def test_diagnostic_cannot_disagree_with_real_strategy(trend):
    bars = flat_bars(239)
    for i in range(len(bars)):
        price = D("100") + D(trend) * D(i) / D("100")
        bars[i][4] = str(price)
    got = diagnosis.explain_paper_signal(bars)
    expected = core.crossover_signal(bars)
    assert got["candidate"] == expected


@pytest.mark.parametrize("bad", [None, "NaN", "Infinity", "-1", "0", True])
def test_invalid_prices_cannot_be_reported_as_clean(bad):
    bars = flat_bars()
    bars[-1][4] = bad
    with pytest.raises(ValueError, match="invalid_paper_close"):
        diagnosis.explain_paper_signal(bars)


def test_less_than_202_bars_is_unknown_not_a_signal():
    with pytest.raises(ValueError, match="insufficient_paper_signal_bars"):
        diagnosis.explain_paper_signal(flat_bars(201))


def test_aggregator_counts_supplied_snapshots_only():
    result = diagnosis.count_paper_filter_reasons([flat_bars(), flat_bars()])
    assert result["reason_counts"] == {"NO_EMA_CROSS": 2}
    assert result["snapshots_checked"] == 2
    assert result["market_source_authenticated"] is False
    assert result["orders_sent"] is False


def test_invalid_snapshot_sequence_rejected():
    with pytest.raises(ValueError, match="invalid_snapshot_sequence"):
        diagnosis.count_paper_filter_reasons(None)


def test_paper_scanner_only_adds_observation_for_missing_signal(tmp_path, monkeypatch):
    class FakeExchange:
        def close(self):
            pass

    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("FUTURES_SYMBOL", "BTC/USDT:USDT")
    monkeypatch.setenv("TIMEFRAME", "15m")
    monkeypatch.setenv("PAPER_START_EQUITY", "37.50")
    monkeypatch.setenv("PAPER_LEDGER", str(tmp_path / "ledger.json"))
    monkeypatch.setenv("LEVERAGE", "2")
    monkeypatch.setattr(scanner, "closed_futures_bars",
                        lambda symbol, timeframe: (FakeExchange(), {}, flat_bars()))
    monkeypatch.setattr(scanner, "approve_paper_portfolio_entry",
                        lambda *args: pytest.fail("must not approve absent signal"))
    out = io.StringIO()
    with redirect_stdout(out):
        scanner.main()
    result = json.loads(out.getvalue())
    assert result["mode"] == "paper"
    assert result["signal"] is None
    assert result["entry"] is None
    assert result["signal_filter"]["condition"] == "NO_EMA_CROSS"
    assert result["signal_filter"]["candidate"] is None
    assert result["signal_filter"]["orders_sent"] is False
    state = json.loads((tmp_path / "ledger.json").read_text())
    assert state["position"] is None
    assert state["history"] == []


def test_paper_live_mode_cannot_be_enabled_by_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("PAPER_LEDGER", str(tmp_path / "paper.json"))
    with pytest.raises(SystemExit, match="LIVE TRADING DISABLED"):
        scanner.main()
    assert not (tmp_path / "paper.json").exists()
