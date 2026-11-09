"""Injectable research adapters for MongoDB and CCXT Pro.

Importing this module does not connect to external services. No trade API.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

logger = logging.getLogger(__name__)


class AtlasResearchStore:
    """Mongo adapter with a 2s handshake and idempotent signal writes."""

    def __init__(self, client: Any, database: str = "signalpilot_research"):
        self.client = client
        self.db = client[database]
        self.snapshots = self.db["l2_snapshots"]
        self.signals = self.db["obi_signals"]

    @classmethod
    async def connect(cls, uri: str, client_factory: Callable[..., Any]) -> AtlasResearchStore:
        client = client_factory(
            uri, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000,
            socketTimeoutMS=2000, maxPoolSize=10,
        )
        try:
            await asyncio.wait_for(client.admin.command("ping"), timeout=2.0)
        except BaseException:
            client.close()
            raise
        return cls(client)

    async def setup(self) -> None:
        await self.snapshots.create_index([("venue", 1), ("asset", 1), ("received_ms", -1)])
        await self.snapshots.create_index("expireAt", expireAfterSeconds=0)
        await self.signals.create_index([("asset", 1), ("timestamp_ms", -1)])
        # Deliberately no TTL index on signals.

    async def write_snapshot(self, document: dict[str, Any]) -> None:
        await self.snapshots.insert_one(document)

    async def upsert_signal(self, document: dict[str, Any]) -> None:
        await self.signals.update_one(
            {"_id": document["_id"]}, {"$setOnInsert": document}, upsert=True
        )

    async def find_causal_snapshot(
        self, venue: str, asset: str, target_ms: int, tolerance_ms: int = 6000
    ) -> dict[str, Any] | None:
        from research.core_engine_v3_9 import historical_query

        return await self.snapshots.find_one(
            historical_query(venue, asset, target_ms, tolerance_ms),
            sort=[("received_ms", -1)],
        )

    async def close(self) -> None:
        self.client.close()


class CcxtOrderBookSource:
    """Owns one exchange connection per adapter; reconnects with backoff."""

    def __init__(
        self, exchange_factory: Callable[[], Any], asset: str, *,
        venue: str, limit: int = 20, max_backoff_s: float = 60.0,
    ):
        self.exchange_factory = exchange_factory
        self.asset = asset
        self.venue = venue
        self.limit = limit
        self.max_backoff_s = max_backoff_s
        self._exchange: Any = None
        self._closed = False
        self._close_lock = asyncio.Lock()

    async def watch(self) -> AsyncIterator[dict[str, Any]]:
        delay = 1.0
        while not self._closed:
            exchange = None
            try:
                exchange = self.exchange_factory()
                self._exchange = exchange
                await exchange.load_markets()
                from research.l2_validation import find_swap_symbol

                symbol = find_swap_symbol(list(exchange.markets.values()), self.asset)
                while not self._closed:
                    book = await exchange.watch_order_book(symbol, self.limit)
                    delay = 1.0
                    yield {"venue": self.venue, "asset": self.asset, "symbol": symbol,
                           "book": book, "contract_size": exchange.market(symbol).get("contractSize", 1)}
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - third-party exchange exceptions vary
                logger.warning("L2 stream disconnected for %s/%s: %s", self.venue, self.asset, type(exc).__name__)
                if self._closed:
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_backoff_s)
            finally:
                if exchange is not None:
                    await self._close_exchange(exchange)

    async def _close_exchange(self, exchange: Any) -> None:
        async with self._close_lock:
            if self._exchange is exchange:
                self._exchange = None
                await exchange.close()

    async def close(self) -> None:
        self._closed = True
        if self._exchange is not None:
            await self._close_exchange(self._exchange)
