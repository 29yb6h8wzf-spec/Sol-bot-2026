"""Pure capacity guard for research L2 snapshot ingestion.

TTL deletes old records eventually; it is not an ingestion quota.
"""
from dataclasses import dataclass
from math import ceil, isfinite


@dataclass(frozen=True)
class StoragePlan:
    streams: int
    sample_interval_ms: int
    retention_hours: int
    estimated_bytes_per_document: int
    budget_bytes: int

    def __post_init__(self) -> None:
        if min(self.streams, self.sample_interval_ms, self.retention_hours,
               self.estimated_bytes_per_document, self.budget_bytes) <= 0:
            raise ValueError("storage plan values must be positive")

    @property
    def estimated_documents(self) -> int:
        return self.streams * ceil(self.retention_hours * 3_600_000 / self.sample_interval_ms)

    @property
    def estimated_bytes(self) -> int:
        return self.estimated_documents * self.estimated_bytes_per_document

    def require_capacity(self) -> None:
        if self.estimated_bytes > self.budget_bytes:
            raise ValueError(
                f"snapshot budget exceeded: estimate={self.estimated_bytes} "
                f"budget={self.budget_bytes}"
            )


class SampleGate:
    """Drop excess raw observations deterministically, per stream."""

    def __init__(self, interval_ms: int):
        if interval_ms <= 0:
            raise ValueError("interval_ms must be positive")
        self.interval_ms = interval_ms
        self._last: dict[tuple[str, str], int] = {}

    def accept(self, venue: str, asset: str, received_ms: int) -> bool:
        if not isfinite(received_ms) or received_ms < 0:
            raise ValueError("invalid timestamp")
        key = (venue, asset)
        previous = self._last.get(key)
        if previous is not None and received_ms < previous:
            raise ValueError("nonmonotonic timestamp")
        if previous is not None and received_ms - previous < self.interval_ms:
            return False
        self._last[key] = received_ms
        return True
