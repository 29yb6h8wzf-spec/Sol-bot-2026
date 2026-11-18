"""Tests for the offline score report reader and its fail-closed inputs."""
import io
import unittest

from futures_engine.research_setup_score_report import build_report


class ScoreReportTests(unittest.TestCase):
    def test_replay_with_two_symbols(self):
        source = io.StringIO(
            '{"symbol":"SOL/USDT:USDT","setups":[{"strategy":"RSI_BOLL","direction":"LONG","score":80}]}\n'
            '{"symbol":"XRP/USDT:USDT","setups":[{"strategy":"MACD_VOLUME","direction":"SHORT","score":85}]}\n'
            '{"symbol":"SOL/USDT:USDT","setups":[]}\n'
        )
        report = build_report(source)
        self.assertEqual(report["totals"]["scans"], 3)
        self.assertEqual(report["totals"]["setups"], 2)
        self.assertEqual(report["totals"]["80_84"], 1)
        self.assertEqual(report["totals"]["85_plus"], 1)
        self.assertEqual(report["totals"]["no_setup_scans"], 1)
        self.assertFalse(report["execution_authorized"])

    def test_invalid_or_empty_replay_rejected(self):
        for raw in ("", " \n", "{invalid}\n",
                    '{"symbol":"BTC/USDT:USDT","setups":[]}\n',
                    '{"symbol":"SOL/USDT:USDT","setups":{}}\n'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    build_report(io.StringIO(raw))


if __name__ == "__main__":
    unittest.main()
