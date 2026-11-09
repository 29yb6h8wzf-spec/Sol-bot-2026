"""Isolated, offline-testable L2 async pipeline skeleton.

No exchange credentials, trading functions, or production deployment hooks.
Adapters are injected and can be backed by mocks in CI.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol

from research.l2_validation import BookMetrics, normalize_book

LOG = logging.getLogger(__name__)


class BookSource(Protocol):
    def watch(self) -> AsyncIterator[dict[str, Any]]: ...
    async def close(self) -> None: ...


class Sink(Protocol):
    async def write(self, item: BookMetrics) -> None: ...
    async def close(self) -> None: ...


async def retry_stream(
    factory: Callable[[], AsyncIterator[dict[str, Any]]],
    consume: Callable[[dict[str, Any]], Awaitable[None]],
    stop: asyncio.Event,
    *,
    initial_delay: float = 0.1,
    max_delay: float = 5.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Reconnect after recoverable stream failures; never swallow cancellation."""
    delay = initial_delay
    while not stop.is_set():
        try:
            async for book in factory():
                if stop.is_set():
                    return
                await consume(book)
                delay = initial_delay
            if stop.is_set():
                return
            raise ConnectionError("stream ended unexpectedly")
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("Stream failed; reconnecting in %.2fs", delay)
            if stop.is_set():
                return
            await sleep(delay)
            delay = min(delay * 2, max_delay)


class ResearchPipeline:
    """Single-writer queue with explicit shutdown and bounded drain timeout."""

    def __init__(self, source: BookSource, sink: Sink, *, max_queue: int = 1000):
        self.source = source
        self.sink = sink
        self.queue: asyncio.Queue[BookMetrics] = asyncio.Queue(maxsize=max_queue)
        self.stop = asyncio.Event()
        self._producer: asyncio.Task[None] | None = None
        self._writer: asyncio.Task[None] | None = None
        self.write_failures = 0

    async def _consume(self, book: dict[str, Any]) -> None:
        metrics = normalize_book(book)
        await self.queue.put(metrics)

    async def _writer_loop(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                await self.sink.write(item)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.write_failures += 1
                LOG.exception("Sink write failed; record not persisted")
            finally:
                self.queue.task_done()

    async def start(self) -> None:
        if self._producer is not None:
            raise RuntimeError("pipeline already started")
        self._writer = asyncio.create_task(self._writer_loop())
        self._producer = asyncio.create_task(
            retry_stream(self.source.watch, self._consume, self.stop)
        )

    async def shutdown(self, *, drain_timeout: float = 10.0) -> None:
        self.stop.set()
        if self._producer:
            self._producer.cancel()
            with suppress(asyncio.CancelledError):
                await self._producer
        try:
            await asyncio.wait_for(self.queue.join(), timeout=drain_timeout)
        finally:
            if self._writer:
                self._writer.cancel()
                with suppress(asyncio.CancelledError):
                    await self._writer
            await self.source.close()
            await self.sink.close()
        if self.write_failures:
            raise RuntimeError(f"{self.write_failures} sink writes failed")
