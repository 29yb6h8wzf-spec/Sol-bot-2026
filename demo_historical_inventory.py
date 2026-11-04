"""Read-only historical Binance DEMO trade inventory; never authorizes execution."""
from datetime import datetime, timedelta, timezone
from demo_account_observer import assert_demo
from demo_trade_attribution import SYMBOLS


def inventory(exchange, start_day, end_day, *, limit=1000):
    assert_demo(exchange)
    start = datetime.strptime(start_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    count = (end - start).days + 1
    if not 1 <= count <= 7 or not 1 <= limit <= 1000:
        raise ValueError("invalid_historical_window")
    days = []
    for i in range(count):
        day = start + timedelta(days=i)
        since = int(day.timestamp() * 1000)
        until = int((day + timedelta(days=1)).timestamp() * 1000)
        fills = 0
        for symbol in SYMBOLS:
            assert_demo(exchange)
            batch = exchange.fetch_my_trades(symbol, since=since, limit=limit)
            if not isinstance(batch, list) or len(batch) >= limit:
                raise ValueError("incomplete_historical_page")
            seen = set()
            for trade in batch:
                if not isinstance(trade, dict) or trade.get("symbol") != symbol:
                    raise ValueError("invalid_historical_trade")
                ts = trade.get("timestamp")
                if type(ts) is not int or ts < since:
                    raise ValueError("invalid_historical_timestamp")
                if ts >= until:
                    continue
                trade_id = trade.get("id")
                if not isinstance(trade_id, (str, int)) or not str(trade_id).isdecimal():
                    raise ValueError("invalid_historical_identity")
                if str(trade_id) in seen:
                    raise ValueError("duplicate_historical_trade")
                seen.add(str(trade_id))
                fills += 1
        days.append({"day": day.date().isoformat(), "observed_fills": fills,
                     "scope": "four_symbols_only"})
    return {"status": "HISTORICAL_INVENTORY_ONLY", "days": days,
            "historical_reconciliation_complete": False,
            "execution_authorized": False, "orders_sent": False}
