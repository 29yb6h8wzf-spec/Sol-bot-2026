"""Research-only L2 ingestion bridge with storage preflight and sampling.

No network connection is opened here. Caller owns the source and writer lifecycles.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from research.core_engine_v3_9 import ResearchWriter
from research.l2_capacity import SampleGate, StoragePlan
from research.l2_validation import normalize_book, snapshot_expiry


class ResearchIngestor:
    def __init__(self, writer: ResearchWriter, plan: StoragePlan):
        plan.require_capacity()
        if writer.cfg.sample_interval_ms != plan.sample_interval_ms:
            raise ValueError("sampling interval mismatch")
        self.writer = writer
        self.plan = plan
        self.gate = SampleGate(plan.sample_interval_ms)
        self.accepted = 0
        self.sampled_out = 0

    def ingest(self, message: dict[str, Any], received_ms: int) -> bool:
        venue = str(message["venue"])
        asset = str(message["asset"])
        if not self.gate.accept(venue, asset, received_ms):
            self.sampled_out += 1
            return False
        metrics = normalize_book(message["book"], float(message["contract_size"]))
        document = {
            "venue": venue,
            "asset": asset,
            "received_ms": received_ms,
            "mid_price": metrics.mid_price,
            "obi": metrics.obi,
            "best_bid": metrics.best_bid,
            "best_ask": metrics.best_ask,
            "expireAt": snapshot_expiry(received_ms, self.writer.cfg.ttl_seconds),
        }
        written = self.writer.submit("snapshots", document)
        if written:
            self.accepted += 1
        return written

    async def consume(self, source: AsyncIterator[dict[str, Any]], clock_ms: Any) -> None:
        """Capture receipt time at source delivery, before persistence."""
        async for message in source:
            if self.writer.stop.is_set():
                break
            self.ingest(message, int(clock_ms()))
