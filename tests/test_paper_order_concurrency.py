"""Offline concurrency acceptance tests for durable paper orders."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D

from research.paper_order_store import DurablePaperOrders


def test_concurrent_duplicate_opens_have_one_durable_record(tmp_path):
    path = tmp_path / "concurrent.sqlite3"

    def open_same(_):
        return DurablePaperOrders(path).open(
            "same-signal", "LONG", "1", "100", "98", "104", 100
        )

    DurablePaperOrders(path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(open_same, range(24)))
    assert all(result == results[0] for result in results)
    assert DurablePaperOrders(path).get("same-signal") == results[0]


def test_concurrent_closes_do_not_double_count_fees(tmp_path):
    path = tmp_path / "concurrent-close.sqlite3"
    store = DurablePaperOrders(path)
    store.open("same-signal", "LONG", "1", "100", "98", "104", 100)

    def close_same(_):
        return DurablePaperOrders(path).update(
            "same-signal", "105", "99", "104", 105
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(close_same, range(24)))
    assert all(result == results[0] for result in results)
    assert results[0].status == "EXECUTED_TP"
    assert results[0].net_pnl < results[0].gross_pnl
    assert DurablePaperOrders(path).get("same-signal") == results[0]
