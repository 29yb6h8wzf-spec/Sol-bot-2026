"""Offline crash/restart and transactional UAT for durable paper trades."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from research.paper_order_store import DurablePaperOrders


def test_reopen_after_restart_is_idempotent(tmp_path):
    path = tmp_path / "restart.sqlite3"
    first = DurablePaperOrders(path).open("signal-1", "LONG", "1", "100", "98", "104", 100)
    second = DurablePaperOrders(path).open("signal-1", "LONG", "1", "110", "108", "114", 200)
    assert second == first


def test_failed_update_keeps_durable_state(tmp_path):
    path = tmp_path / "rollback.sqlite3"
    store = DurablePaperOrders(path)
    original = store.open("signal-2", "LONG", "1", "100", "98", "104", 100)
    with pytest.raises(ValueError):
        store.update("signal-2", "90", "110", "100", 101)
    assert DurablePaperOrders(path).get("signal-2") == original


def test_concurrent_restart_replay_preserves_single_close(tmp_path):
    path = tmp_path / "replay.sqlite3"
    DurablePaperOrders(path).open("signal-3", "LONG", "1", "100", "98", "104", 100)

    def replay(_):
        return DurablePaperOrders(path).update("signal-3", "105", "99", "104", 105)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(replay, range(24)))
    assert all(result == results[0] for result in results)
    assert results[0].status == "EXECUTED_TP"
    assert DurablePaperOrders(path).get("signal-3") == results[0]
