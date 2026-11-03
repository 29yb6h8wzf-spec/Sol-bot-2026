"""Read-only Binance USDT-M DEMO income reconciliation (UTC day).

This is an ACCOUNT-WIDE observation, not a SignalPilot allocation ledger.
Never creates orders or an execution-authorizing risk snapshot.
"""
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from demo_account_observer import demo_exchange, assert_demo, save_observation

OUTPUT = "/opt/signalpilot/demo-pnl-observation.json"
INCOME_TYPES = frozenset(("REALIZED_PNL", "COMMISSION", "FUNDING_FEE"))
MAX_PAGES = 10
PAGE_SIZE = 1000
DAILY_LOSS_CAP = Decimal("7.50")


def decimal(value):
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError("invalid_income_amount") from None
    if not number.is_finite():
        raise ValueError("nonfinite_income_amount")
    return number


def fetch_utc_day_income(exchange, *, now_ms=None, page_size=PAGE_SIZE):
    assert_demo(exchange)
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if now_ms <= 0 or not 1 <= page_size <= 1000:
        raise ValueError("invalid_time_or_page_size")
    utc = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    midnight = utc.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(midnight.timestamp() * 1000)
    # Income history is account-wide; a symbol filter would miss fees/funding.
    events = []
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        assert_demo(exchange)
        batch = exchange.fapiPrivateGetIncome({
            "startTime": start_ms, "endTime": now_ms,
            "limit": page_size, "page": page})
        if not isinstance(batch, list):
            raise ValueError("invalid_income_response")
        for row in batch:
            if not isinstance(row, dict):
                raise ValueError("invalid_income_event")
            timestamp = row.get("time")
            tx = row.get("tranId")
            kind = row.get("incomeType")
            asset = row.get("asset")
            if type(timestamp) is not int or not start_ms <= timestamp <= now_ms:
                raise ValueError("income_outside_requested_day")
            if not isinstance(tx, (int, str)) or not str(tx):
                raise ValueError("missing_income_transaction_id")
            if kind not in INCOME_TYPES or asset != "USDT":
                raise ValueError("unsupported_income_event_or_asset")
            amount = decimal(row.get("income"))
            key = (str(tx), str(kind), str(timestamp))
            if key in seen:
                raise ValueError("duplicate_income_event")
            seen.add(key)
            events.append((kind, amount))
        if len(batch) < page_size:
            return start_ms, events
    raise ValueError("income_history_pagination_exhausted")


def summarize(events, *, start_ms, observed_at):
    totals = {kind: Decimal("0") for kind in INCOME_TYPES}
    for kind, amount in events:
        if kind not in totals:
            raise ValueError("unknown_income_type")
        totals[kind] += decimal(amount)
    net = sum(totals.values(), Decimal("0"))
    return {
        "source": "binance_demo_account_wide_income_read_only",
        "observed_at": observed_at,
        "day_start_utc_ms": start_ms,
        "income_events": len(events),
        "realized_pnl_usdt": str(totals["REALIZED_PNL"]),
        "commissions_usdt": str(totals["COMMISSION"]),
        "funding_usdt": str(totals["FUNDING_FEE"]),
        "net_income_usdt": str(net),
        "daily_loss_threshold_usdt": str(DAILY_LOSS_CAP),
        "daily_loss_threshold_reached": net <= -DAILY_LOSS_CAP,
        "scope": "whole_demo_account_not_150_usdt_strategy_allocation",
        "allocation_ledger_reconciled": False,
        "risk_snapshot_approved": False,
        "execution_authorized": False,
        "orders_sent": False,
    }


def observe(exchange, *, now_ms=None, page_size=PAGE_SIZE):
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    start_ms, events = fetch_utc_day_income(exchange, now_ms=now_ms,
                                             page_size=page_size)
    return summarize(events, start_ms=start_ms, observed_at=now_ms // 1000)


def main():
    exchange = demo_exchange()
    try:
        result = observe(exchange)
        save_observation(result, OUTPUT)
        print(json.dumps(result, sort_keys=True))
    finally:
        if hasattr(exchange, "close"):
            exchange.close()


if __name__ == "__main__":
    main()
