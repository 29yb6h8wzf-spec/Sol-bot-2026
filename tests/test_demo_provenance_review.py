"""Offline read-only provenance audit tests; fake exchange never places orders."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from demo_provenance_review import classify_fills, ReviewError
from demo_provenance_observer import inspect


def fill(oid="100", tid="1", fee="0.01"):
    return {"symbol": "BTC/USDT:USDT", "order_id": oid, "trade_id": tid,
            "realized_pnl_usdt": "-0.1", "fee_usdt": fee}


def receipt(oid="100", sid="s1", leg="entry"):
    client = "SPDEMO-" + hashlib.sha256((sid + ":" + leg).encode()).hexdigest()[:24]
    return {"symbol": "BTC/USDT:USDT", "order_id": oid,
            "client_order_id": client, "signal_id": sid, "leg": leg}


def lookup(oid="100", client="MANUAL-1", confirmed=True):
    return {"symbol": "BTC/USDT:USDT", "order_id": oid,
            "client_order_id": client, "confirmed": confirmed}


class ReviewTests(unittest.TestCase):
    def test_multiple_fills_one_order(self):
        r = classify_fills([fill(), fill(tid="2")], [lookup()], [])
        self.assertEqual((r["total_fills"], r["unique_orders"], r["unattributed_fills"]), (2, 1, 2))

    def test_verified_receipt(self):
        rec = receipt()
        r = classify_fills([fill()], [lookup(client=rec["client_order_id"])], [rec])
        self.assertEqual(r["verified_signalpilot_fills"], 1)
        self.assertFalse(r["execution_authorized"])

    def test_unregistered_prefix_not_owned(self):
        r = classify_fills([fill()], [lookup(client=receipt()["client_order_id"])], [])
        self.assertEqual(r["order_classifications"], {"UNREGISTERED_SPDEMO_TAG": 1})

    def test_mismatched_registry_not_owned(self):
        r = classify_fills([fill()], [lookup(client="OTHER")], [receipt()])
        self.assertEqual(r["order_classifications"], {"REGISTRY_EXCHANGE_MISMATCH": 1})

    def test_unverified_order_not_owned(self):
        r = classify_fills([fill()], [lookup(confirmed=False)], [receipt()])
        self.assertEqual(r["unattributed_fills"], 1)

    def test_missing_lookup_not_owned(self):
        r = classify_fills([fill()], [], [])
        self.assertEqual(r["order_classifications"], {"ORDER_LOOKUP_UNVERIFIED": 1})

    def test_duplicate_fill_rejected(self):
        with self.assertRaisesRegex(ReviewError, "duplicate_fill"):
            classify_fills([fill(), fill()], [], [])

    def test_duplicate_lookup_rejected(self):
        with self.assertRaisesRegex(ReviewError, "duplicate_lookup"):
            classify_fills([fill()], [lookup(), lookup()], [])

    def test_bad_receipt_rejected(self):
        rec = receipt()
        rec["client_order_id"] = "SPDEMO-fake"
        with self.assertRaisesRegex(ReviewError, "invalid_receipt_client"):
            classify_fills([fill()], [lookup()], [rec])

    def test_nonfinite_amount_rejected(self):
        bad = fill()
        bad["realized_pnl_usdt"] = "NaN"
        with self.assertRaisesRegex(ReviewError, "nonfinite_amount"):
            classify_fills([bad], [lookup()], [])

    def test_negative_fee_rejected(self):
        with self.assertRaisesRegex(ReviewError, "negative_fee"):
            classify_fills([fill(fee="-1")], [lookup()], [])

    def test_empty_still_not_authorized(self):
        r = classify_fills([], [], [])
        self.assertFalse(r["allocation_ledger_reconciled"])
        self.assertFalse(r["execution_authorized"])

    def test_missing_receipt_is_not_strategy_ownership(self):
        r = classify_fills([fill()], [lookup(client="SPDEMO-something")], [])
        self.assertEqual(r["verified_signalpilot_fills"], 0)

    def test_duplicate_receipt_client_rejected(self):
        with self.assertRaisesRegex(ReviewError, "duplicate_receipt"):
            classify_fills([], [], [receipt(), receipt(oid="200")])

    def test_missing_fee_rejected(self):
        bad = fill()
        bad.pop("fee_usdt")
        with self.assertRaises(ReviewError):
            classify_fills([bad], [], [])

    def test_live_endpoint_guard(self):
        class Fake:
            urls = {"api": "https://fapi.binance.com"}
        with self.assertRaisesRegex(RuntimeError, "non_demo_endpoint_blocked"):
            inspect(Fake(), registry_path=Path("/no-such-file"))

    def test_fake_exchange_no_registry_stays_unattributed(self):
        class Fake:
            urls = {"api": "https://demo-fapi.binance.com"}
            def fetch_my_trades(self, symbol, since=None, limit=None):
                if symbol != "BTC/USDT:USDT":
                    return []
                return [{"symbol": symbol, "timestamp": since + 1000,
                         "order": "100", "id": "1",
                         "fee": {"currency": "USDT", "cost": 0.01},
                         "info": {"realizedPnl": "-0.1"}}]
            def fetch_order(self, oid, symbol):
                return {"id": oid, "symbol": symbol, "clientOrderId": "MANUAL-1"}
        with tempfile.TemporaryDirectory() as tmp:
            report = inspect(Fake(), registry_path=Path(tmp) / "missing.json",
                             now_ms=1793707200000)
        self.assertEqual(report["unattributed_fills"], 1)
        self.assertEqual(report["unique_orders"], 1)
        self.assertFalse(report["execution_authorized"])


if __name__ == "__main__":
    unittest.main()
