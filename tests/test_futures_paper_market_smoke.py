"""Offline tests for public market smoke evidence; no Binance access."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from futures_engine import market_smoke


class FakeExchange:
    def close(self):
        pass


class PublicMarketSmokeTests(unittest.TestCase):
    def test_success_writes_auditable_read_only_evidence(self):
        bars = [[i * 300000, 100, 101, 99, 100, 10] for i in range(1000)]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(market_smoke, "closed_futures_bars", return_value=(FakeExchange(), {}, bars)), patch.object(market_smoke.sys, "argv", ["market_smoke", tmp]):
                market_smoke.main()
            data = json.loads((Path(tmp) / "market-smoke.json").read_text())
            self.assertEqual(len(data["results"]), 4)
            self.assertTrue(all(r["status"] == "ok" for r in data["results"]))
            self.assertFalse(data["authenticated"])
            self.assertFalse(data["orders_submitted"])
            self.assertFalse(data["paper_trades_created"])

    def test_failure_saves_error_and_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(market_smoke, "closed_futures_bars", side_effect=RuntimeError("network unavailable")), patch.object(market_smoke.sys, "argv", ["market_smoke", tmp]):
                with self.assertRaises(SystemExit):
                    market_smoke.main()
            data = json.loads((Path(tmp) / "market-smoke.json").read_text())
            self.assertEqual(len(data["results"]), 4)
            self.assertTrue(all(r["status"] == "error" for r in data["results"]))


if __name__ == "__main__":
    unittest.main()
