"""Offline ingestion bridge tests."""
import asyncio

import pytest

from research.core_engine_v3_9 import ResearchConfig, ResearchWriter
from research.l2_capacity import StoragePlan
from research.l2_ingestion import ResearchIngestor


class FakeStore:
    def __init__(self):
        self.snapshots = []
        self.closed = False

    async def write_snapshot(self, doc):
        self.snapshots.append(doc)

    async def upsert_signal(self, doc):
        pass

    async def close(self):
        self.closed = True


def message(venue="okx"):
    return {"venue": venue, "asset": "SOL", "contract_size": 1,
            "book": {"bids": [[100, 2]], "asks": [[101, 1]]}}


def test_ingestion_samples_and_drains():
    async def scenario():
        store = FakeStore()
        writer = ResearchWriter(store, ResearchConfig(sample_interval_ms=10000))
        plan = StoragePlan(6, 10000, 96, 1024, 512 * 1024 * 1024)
        ingestor = ResearchIngestor(writer, plan)
        writer.start()
        assert ingestor.ingest(message(), 100000)
        assert not ingestor.ingest(message(), 105000)
        assert ingestor.ingest(message("bybit"), 105000)
        await writer.shutdown()
        assert len(store.snapshots) == 2
        assert store.snapshots[0]["received_ms"] == 100000
        assert store.closed
    asyncio.run(scenario())


def test_ingestion_fails_preflight_before_writes():
    store = FakeStore()
    writer = ResearchWriter(store, ResearchConfig(sample_interval_ms=100))
    with pytest.raises(ValueError, match="budget exceeded"):
        ResearchIngestor(writer, StoragePlan(6, 100, 96, 1024, 512 * 1024 * 1024))
    assert store.snapshots == []


def test_ingestion_rejects_interval_mismatch():
    writer = ResearchWriter(FakeStore(), ResearchConfig(sample_interval_ms=100))
    with pytest.raises(ValueError, match="interval mismatch"):
        ResearchIngestor(writer, StoragePlan(6, 10000, 96, 1024, 512 * 1024 * 1024))


def test_six_streams_share_bounded_writer_without_cross_sampling():
    async def scenario():
        store = FakeStore()
        writer = ResearchWriter(store, ResearchConfig(sample_interval_ms=10000, queue_size=12))
        ingestor = ResearchIngestor(
            writer, StoragePlan(6, 10000, 96, 1024, 512 * 1024 * 1024)
        )
        writer.start()
        for venue in ("binance", "bybit", "okx"):
            for asset in ("SOL", "XRP"):
                event = message(venue)
                event["asset"] = asset
                assert ingestor.ingest(event, 100000)
                assert not ingestor.ingest(event, 105000)
        await writer.shutdown()
        assert len(store.snapshots) == 6
        assert ingestor.accepted == 6
        assert ingestor.sampled_out == 6
        assert writer.dropped_snapshots == 0

    asyncio.run(scenario())


def test_saturated_queue_counts_snapshot_drops():
    store = FakeStore()
    writer = ResearchWriter(store, ResearchConfig(sample_interval_ms=10000, queue_size=1))
    ingestor = ResearchIngestor(
        writer, StoragePlan(6, 10000, 96, 1024, 512 * 1024 * 1024)
    )
    assert ingestor.ingest(message("okx"), 100000)
    assert not ingestor.ingest(message("bybit"), 100000)
    assert writer.dropped_snapshots == 1
