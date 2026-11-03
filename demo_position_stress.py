"""Read-only Binance USDT-M Demo position stress report; never sends orders."""
import json
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from demo_account_observer import demo_exchange, assert_demo, save_observation
from demo_risk_monitor import check_observation

OUTPUT = "/opt/signalpilot/demo-position-stress.json"
ROOT = Path("/opt/signalpilot")
DAILY_CAP = Decimal("7.50")
COST_RATE = Decimal("0.002")


def dec(value):
    try:
        d = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError("invalid_position_number") from None
    if not d.is_finite():
        raise ValueError("nonfinite_position_number")
    return d


def evaluate(exchange, exposure, *, now=None):
    assert_demo(exchange)
    now = int(time.time()) if now is None else int(now)
    check_observation(exposure, "binance_demo_account_wide_unrealized_read_only", now)
    rows = exchange.fetch_positions()
    if not isinstance(rows, list):
        raise ValueError("invalid_positions")
    seen = set()
    symbols = []
    notional = Decimal("0")
    unrealized = Decimal("0")
    for p in rows:
        if not isinstance(p, dict) or not isinstance(p.get("info"), dict):
            raise ValueError("invalid_position")
        info = p["info"]
        qty = dec(info.get("positionAmt"))
        if qty == 0:
            continue
        symbol = p.get("symbol")
        if not isinstance(symbol, str) or not symbol.endswith("/USDT:USDT"):
            raise ValueError("unsupported_position_symbol")
        if symbol in seen:
            raise ValueError("hedge_or_duplicate_position")
        seen.add(symbol)
        symbols.append(symbol)
        mark = dec(info.get("markPrice"))
        if mark <= 0:
            raise ValueError("invalid_mark_price")
        notional += abs(qty) * mark
        unrealized += dec(info.get("unRealizedProfit"))
    if (sorted(symbols) != sorted(exposure.get("exposed_symbols", [])) or
            len(symbols) != exposure.get("open_position_count") or
            unrealized != dec(exposure.get("unrealized_pnl_usdt"))):
        raise ValueError("position_observation_mismatch")
    loss2 = notional * (Decimal("0.02") + COST_RATE)
    loss5 = notional * (Decimal("0.05") + COST_RATE)
    return {
        "source": "binance_demo_position_stress_read_only",
        "observed_at": now,
        "position_count": len(symbols),
        "gross_notional_usdt": str(notional),
        "unrealized_pnl_usdt": str(unrealized),
        "stress_loss_2pct_usdt": str(loss2),
        "stress_loss_5pct_usdt": str(loss5),
        "stress_2pct_exceeds_daily_cap": loss2 >= DAILY_CAP,
        "stress_5pct_exceeds_daily_cap": loss5 >= DAILY_CAP,
        "assumed_cost_rate": str(COST_RATE),
        "scope": "account_wide_hypothetical_not_stop_loss_guarantee",
        "allocation_ledger_reconciled": False,
        "execution_authorized": False,
        "orders_sent": False,
    }


def main():
    exchange = demo_exchange()
    try:
        path = ROOT / "demo-exposure-observation.json"
        st = path.lstat()
        if not path.is_file() or path.is_symlink() or st.st_uid != 0 or st.st_mode & 0o077:
            raise ValueError("untrusted_exposure_file")
        exposure = json.loads(path.read_text(encoding="utf-8"))
        result = evaluate(exchange, exposure)
        save_observation(result, OUTPUT)
        print(json.dumps(result, sort_keys=True))
    finally:
        if hasattr(exchange, "close"):
            exchange.close()


if __name__ == "__main__":
    main()
