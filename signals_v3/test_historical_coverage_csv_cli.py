"""Offline CSV adapter regression tests."""
import json
import tempfile
import unittest
from pathlib import Path

from signals_v3.historical_coverage_csv_cli import run, load_funding, read_times


class CsvCoverageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def file(self, name, content):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_local_csv_to_gap_report(self):
        funding = self.file("funding.csv", "symbol,funding_time_ms,funding_rate\nSOLUSDT,1000,0.0001\n")
        funding_times = self.file("funding_times.csv", "timestamp_ms\n1000\n2000\n")
        orderbook = self.file("orderbook.csv", "symbol,timestamp_ms,spread_bps,bid_depth_10bps_usd,ask_depth_10bps_usd\nSOLUSDT,1000,2,1000,1000\n")
        decisions = self.file("decisions.csv", "timestamp_ms\n1000\n2000\n")
        result = json.loads(run(funding, funding_times, orderbook, decisions, "SOLUSDT", 100))
        self.assertEqual(result["gap_timestamps_ms"]["funding_missing"], [2000])
        self.assertEqual(result["gap_timestamps_ms"]["orderbook_stale"], [2000])
        self.assertFalse(result["historical_evidence_verified"])

    def test_missing_columns_fail(self):
        path = self.file("bad.csv", "symbol,funding_rate\nSOLUSDT,0.1\n")
        with self.assertRaisesRegex(ValueError, "missing_csv_columns"):
            load_funding(path)

    def test_duplicate_columns_fail(self):
        path = self.file("duplicate.csv", "timestamp_ms,timestamp_ms\n1000,1000\n")
        with self.assertRaisesRegex(ValueError, "invalid_csv_columns"):
            read_times(path)

    def test_invalid_timestamp_fail(self):
        path = self.file("invalid.csv", "timestamp_ms\n1000.5\n")
        with self.assertRaisesRegex(ValueError, "invalid_schedule_timestamp"):
            read_times(path)

    def test_extra_csv_cell_fail(self):
        path = self.file("extra.csv", "timestamp_ms\n1000,2000\n")
        with self.assertRaisesRegex(ValueError, "invalid_csv_row"):
            read_times(path)


if __name__ == "__main__":
    unittest.main()
