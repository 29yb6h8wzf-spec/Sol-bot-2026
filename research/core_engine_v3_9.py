"""SignalPilot v3.9 research-only core: causal evaluation and safe persistence.

No trading endpoints, exchange credentials, AWS calls, or deployment side effects.
External Mongo and market-data adapters are injected and must be validated separately.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from research.l2_validation import (
    SNAPSHOT_TTL_SECONDS,
    asof_snapshot,
    find_swap_symbol,
    normalize_book,
    snapshot_expiry,
    tracking_complete,
)

LOG = logging.getLogger(__name__)
HORIZONS_MINUTES = (5, 15, 30)


@dataclass(frozen=True)
class ResearchConfig:
    ttl_seconds: int = SNAPSHOT_TTL_SECONDS
    tolerance_ms: int = 6000
    queue_size: int = 1000
    sample_interval_ms: int = 100

    def __post_init__(self) -> None:
        snapshot_expiry(0, self.ttl_seconds)
        if self.tolerance_ms < 0 or self.queue_size <= 0 or self.sample_interval_ms <= 0:
            raise ValueError("invalid research configuration")


def historical_query(venue: str, asset: str, target_ms: int, tolerance_ms: int = 6000) -> dict[str, Any]:
    """Mongo filter: no snapshot received after the evaluation horizon."""
    return {
        "venue": venue,
        "asset": asset,
        "received_ms": {"$gte": target_ms - tolerance_ms, "$lte": target_ms},
    }


def evaluate_horizon(
    signal: dict[str, Any],
    horizon_minutes: int,
    venue_snapshots: dict[str, list[dict[str, Any]]],
    *,
    tolerance_ms: int = 6000,
) -> dict[str, Any]:
    """Evaluate a horizon using only causally available snapshots.

    Missing observations remain explicit missing_data, never fabricated returns.
    """
    if horizon_minutes not in HORIZONS_MINUTES:
        raise ValueError("unsupported horizon")
    target = int(signal["timestamp_ms"]) + horizon_minutes * 60_000
    v1, v2 = signal["venue_lead"], signal["venue_lag"]
    asset = signal["asset"]
    a = asof_snapshot(venue_snapshots.get(v1, []), v1, asset, target, tolerance_ms)
    b = asof_snapshot(venue_snapshots.get(v2, []), v2, asset, target, tolerance_ms)
    if a is None or b is None:
        return {"data_status": "missing_data", "reason": "causal_snapshot_unavailable",
                "target_ms": target}
    initial = signal["initial_prices"]
    r1 = float(a["mid_price"]) / float(initial[v1]["mid"]) - 1
    r2 = float(b["mid_price"]) / float(initial[v2]["mid"]) - 1
    friction = float(signal["entry_friction_fraction"])
    return {
        "data_status": "valid",
        "target_ms": target,
        "sample_drift_ms": max(a["received_ms"], b["received_ms"]) - target,
        "sample_drift_ms_by_venue": {v1: a["received_ms"] - target, v2: b["received_ms"] - target},
        "strategy_A_long_lead_net": r1 - r2 - 2 * friction,
        "strategy_B_short_lead_net": r2 - r1 - 2 * friction,
    }


class DocumentStore(Protocol):
    async def write_snapshot(self, document: dict[str, Any]) -> None: ...
    async def upsert_signal(self, document: dict[str, Any]) -> None: ...
    async def close(self) -> None: ...


class PersistenceError(RuntimeError):
    """A signal was not durably persisted or drain failed."""


class ResearchWriter:
    """Bounded async writer: snapshots may be dropped; signals fail closed."""

    def __init__(self, store: DocumentStore, cfg: ResearchConfig):
        self.store = store
        self.cfg = cfg
        self.queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(
            maxsize=cfg.queue_size
        )
        self.stop = asyncio.Event()
        self.dropped_snapshots = 0
        self.failure: BaseException | None = None
        self._task: asyncio.Task[None] | None = None

    def submit(self, kind: str, doc: dict[str, Any]) -> bool:
        if kind not in ("snapshots", "signals"):
            raise ValueError("unknown collection")
        if self.stop.is_set() or self.failure is not None:
            raise PersistenceError("writer stopped or unhealthy")
        try:
            self.queue.put_nowait((kind, doc))
            return True
        except asyncio.QueueFull as exc:
            if kind == "snapshots":
                self.dropped_snapshots += 1
                LOG.warning("snapshot dropped due to bounded queue saturation")
                return False
            self.stop.set()
            raise PersistenceError("signal queue full; stopping research") from exc

    async def _write_loop(self) -> None:
        while True:
            kind, doc = await self.queue.get()
            try:
                if kind == "signals":
                    await self.store.upsert_signal(doc)
                else:
                    await self.store.write_snapshot(doc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.failure = exc
                self.stop.set()
                LOG.exception("research persistence failed; stopping writer")
                return
            finally:
                self.queue.task_done()

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("writer already started")
        self._task = asyncio.create_task(self._write_loop())

    async def shutdown(self, timeout: float = 10.0) -> None:
        self.stop.set()
        try:
            if self._task is None:
                if not self.queue.empty():
                    raise PersistenceError("queued documents without writer")
            elif self.failure is None:
                await asyncio.wait_for(self.queue.join(), timeout=timeout)
        except TimeoutError as exc:
            raise PersistenceError("persistence drain timed out") from exc
        finally:
            if self._task is not None:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
            await self.store.close()
        if self.failure is not None:
            raise PersistenceError("research persistence failed") from self.failure


__all__ = [
    "ResearchConfig", "ResearchWriter", "PersistenceError",
    "evaluate_horizon", "historical_query", "normalize_book",
    "find_swap_symbol", "snapshot_expiry", "tracking_complete",
]
