"""Offline tests for Atlas and CCXT research adapters."""
import asyncio

import pytest

from research.l2_adapters import AtlasResearchStore, CcxtOrderBookSource


class FakeCollection:
    def __init__(self):
        self.indexes = []
        self.upserts = []

    async def create_index(self, spec, **kw):
        self.indexes.append((spec, kw))

    async def update_one(self, filt, update, **kw):
        self.upserts.append((filt, update, kw))

    async def find_one(self, filt, **kw):
        self.query = (filt, kw)
        return None


class FakeClient:
    def __init__(self, fail=False):
        self.closed = False
        self.fail = fail
        self.collections = {}
        self.admin = self

    async def command(self, cmd):
        if self.fail:
            raise TimeoutError("handshake")
        return {"ok": 1}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeDatabase()
        return self.collections[name]

    def close(self):
        self.closed = True


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]


def test_atlas_causal_query_and_idempotent_upsert():
    async def scenario():
        client = FakeClient()
        store = await AtlasResearchStore.connect("fake://", lambda *a, **k: client)
        await store.setup()
        await store.upsert_signal({"_id": "s1", "asset": "SOL"})
        await store.find_causal_snapshot("okx", "SOL", 300000)
        assert store.signals.upserts[0][2]["upsert"]
        assert store.signals.upserts[0][1] == {"$setOnInsert": {"_id": "s1", "asset": "SOL"}}
        assert store.snapshots.query[0]["received_ms"]["$lte"] == 300000
        assert all("expireAfterSeconds" not in opts for _, opts in store.signals.indexes)
        await store.close()
        assert client.closed
    asyncio.run(scenario())


def test_atlas_handshake_failure_closes_client():
    async def scenario():
        client = FakeClient(fail=True)
        with pytest.raises(TimeoutError):
            await AtlasResearchStore.connect("fake://", lambda *a, **k: client)
        assert client.closed
    asyncio.run(scenario())


class FakeExchange:
    def __init__(self):
        self.id = "fake"
        self.closed = False
        self.markets = {"SOL/USDT:USDT": {
            "base": "SOL", "quote": "USDT", "swap": True, "linear": True,
            "symbol": "SOL/USDT:USDT",
        }}

    async def load_markets(self):
        return self.markets

    def market(self, symbol):
        return self.markets[symbol]

    async def watch_order_book(self, symbol, limit):
        return {"bids": [[100, 1]], "asks": [[101, 1]]}

    async def close(self):
        self.closed = True


def test_ccxt_source_streams_and_closes():
    async def scenario():
        exch = FakeExchange()
        source = CcxtOrderBookSource(lambda: exch, "SOL", venue="fake")
        gen = source.watch()
        msg = await anext(gen)
        assert msg["symbol"] == "SOL/USDT:USDT"
        await gen.aclose()
        assert exch.closed
    asyncio.run(scenario())
