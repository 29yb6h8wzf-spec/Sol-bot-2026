"""Offline alternate source tests, no external API access."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from futures_engine import alternate_market_smoke as smoke


class AlternateSourceTests(unittest.TestCase):
    def test_explicit_spot_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(smoke, "inspect", return_value={"symbol": "BTC/USDT", "status": "ok", "closed_candles": 239}), patch.object(smoke.sys, "argv", ["smoke", tmp]):
                smoke.main()
            report = json.loads((Path(tmp) / "alternate-market-smoke.json").read_text())
            self.assertTrue(report["not_binance_futures"])
            self.assertEqual(report["market_type"], "spot")
            self.assertFalse(report["orders_submitted"])
            self.assertFalse(report["paper_trades_created"])

    def test_failure_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(smoke, "inspect", side_effect=ValueError("stale spot candles")), patch.object(smoke.sys, "argv", ["smoke", tmp]):
                with self.assertRaises(SystemExit):
                    smoke.main()
            report = json.loads((Path(tmp) / "alternate-market-smoke.json").read_text())
            self.assertTrue(all(r["status"] == "error" for r in report["results"]))


if __name__ == "__main__":
    unittest.main()
