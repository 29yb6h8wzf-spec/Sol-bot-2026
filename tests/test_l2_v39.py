"""Offline v3.9 causal evaluation and persistence tests."""
import asyncio

import pytest

from research.core_engine_v3_9 import (
    PersistenceError,
    ResearchConfig,
    ResearchWriter,
    evaluate_horizon,
    historical_query,
)


def sample_signal():
    return {
        "timestamp_ms": 1000, "asset": "SOL", "venue_lead": "okx",
        "venue_lag": "bybit", "initial_prices": {
            "okx": {"mid": 100}, "bybit": {"mid": 100}
        }, "entry_friction_fraction": 0.001,
    }


def test_query_is_causal():
    q = historical_query("okx", "SOL", 301000)
    assert q["received_ms"] == {"$gte": 295000, "$lte": 301000}


def test_future_tick_excluded_and_drift_nonpositive():
    sig = sample_signal()
    rows = {
        "okx": [
            {"venue": "okx", "asset": "SOL", "received_ms": 300990, "mid_price": 101},
            {"venue": "okx", "asset": "SOL", "received_ms": 301001, "mid_price": 200},
        ],
        "bybit": [
            {"venue": "bybit", "asset": "SOL", "received_ms": 300995, "mid_price": 100}
        ],
    }
    result = evaluate_horizon(sig, 5, rows)
    assert result["data_status"] == "valid"
    assert result["sample_drift_ms"] == -5
    assert result["strategy_A_long_lead_net"] == pytest.approx(0.008)
    assert all(x <= 0 for x in result["sample_drift_ms_by_venue"].values())


def test_missing_causal_snapshot_not_success():
    sig = sample_signal()
    rows = {
        "okx": [{"venue": "okx", "asset": "SOL", "received_ms": 301001, "mid_price": 101}],
        "bybit": [{"venue": "bybit", "asset": "SOL", "received_ms": 301000, "mid_price": 100}],
    }
    assert evaluate_horizon(sig, 5, rows)["data_status"] == "missing_data"


class FakeStore:
    def __init__(self, fail=False):
        self.fail = fail
        self.written = []
        self.closed = False

    async def write_snapshot(self, doc):
        self.written.append(("snapshots", doc))

    async def upsert_signal(self, doc):
        if self.fail:
            raise OSError("db unavailable")
        self.written.append(("signals", doc))

    async def close(self):
        self.closed = True


def test_writer_drains_signals():
    async def scenario():
        store = FakeStore()
        writer = ResearchWriter(store, ResearchConfig(queue_size=2))
        writer.start()
        writer.submit("signals", {"_id": "test-1"})
        await writer.shutdown()
        assert store.written == [("signals", {"_id": "test-1"})]
        assert store.closed
    asyncio.run(scenario())


def test_writer_fails_hard_on_signal_write_error():
    async def scenario():
        store = FakeStore(fail=True)
        writer = ResearchWriter(store, ResearchConfig())
        writer.start()
        writer.submit("signals", {"_id": "test-2"})
        for _ in range(100):
            if writer.stop.is_set():
                break
            await asyncio.sleep(0.001)
        with pytest.raises(PersistenceError):
            await writer.shutdown()
        assert store.closed
    asyncio.run(scenario())


def test_full_signal_queue_fails_closed():
    async def scenario():
        store = FakeStore()
        writer = ResearchWriter(store, ResearchConfig(queue_size=1))
        writer.submit("signals", {"_id": "one"})
        with pytest.raises(PersistenceError):
            writer.submit("signals", {"_id": "two"})
        with pytest.raises(PersistenceError):
            await writer.shutdown()
        assert store.closed
    asyncio.run(scenario())
