import asyncio

import pytest

from research.core_engine_v3_8 import ResearchPipeline, retry_stream


@pytest.mark.asyncio
async def test_retry_after_disconnect():
    stop = asyncio.Event()
    attempts = []
    received = []

    async def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("temporary")
        yield {"ok": True}

    async def consume(book):
        received.append(book)
        stop.set()

    async def no_sleep(_):
        return None

    await retry_stream(factory, consume, stop, sleep=no_sleep)
    assert len(attempts) == 2
    assert received == [{"ok": True}]


@pytest.mark.asyncio
async def test_shutdown_drains_queue():
    closed = []

    class Source:
        async def watch(self):
            while True:
                yield {"bids": [[100, 3]], "asks": [[102, 1]]}
                await asyncio.sleep(0.01)

        async def close(self):
            closed.append("source")

    class Sink:
        def __init__(self):
            self.written = []

        async def write(self, item):
            await asyncio.sleep(0.001)
            self.written.append(item)

        async def close(self):
            closed.append("sink")

    sink = Sink()
    pipeline = ResearchPipeline(Source(), sink)
    await pipeline.start()
    await asyncio.sleep(0.035)
    await pipeline.shutdown()
    assert sink.written
    assert pipeline.queue.empty()
    assert closed == ["source", "sink"]


@pytest.mark.asyncio
async def test_write_failure_is_reported():
    class Source:
        async def watch(self):
            yield {"bids": [[100, 3]], "asks": [[102, 1]]}
            await asyncio.sleep(10)

        async def close(self):
            pass

    class Sink:
        async def write(self, _):
            raise OSError("db unavailable")

        async def close(self):
            pass

    pipeline = ResearchPipeline(Source(), Sink())
    await pipeline.start()
    await asyncio.sleep(0.03)
    with pytest.raises(RuntimeError, match="sink writes failed"):
        await pipeline.shutdown()
