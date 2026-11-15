import sqlite3
import unittest
from unittest.mock import Mock, patch

from futures_engine.breakout_runner import Journal, tick


class RunnerTimingTest(unittest.TestCase):
    target = 1794676800000

    def invoke(self, readings):
        exchange = Mock()
        exchange.fetch_time.side_effect = readings
        exchange.fapiPrivateV3GetAccount.return_value = {
            "positions": [], "totalMarginBalance": "150", "totalInitialMargin": "0",
            "totalOpenOrderInitialMargin": "0",
        }
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        with patch("futures_engine.breakout_runner.time") as clock, \
             patch("futures_engine.breakout_runner.scan", return_value={"status": "no_candidate"}) as scan:
            clock.time_ns.return_value = readings[-1] * 1_000_000
            status = tick(exchange, Journal(db), self.target)
        return status, clock.sleep, scan

    def test_early_preparation_waits_for_exchange_close(self):
        status, sleep, scan = self.invoke([self.target-5000, self.target+1020])
        sleep.assert_called_once_with(6)
        self.assertEqual(status, "no_candidate")
        self.assertEqual(scan.call_count, 2)
        self.assertEqual(scan.call_args.args[1], self.target)

    def test_late_wakeup_does_not_sleep(self):
        status, sleep, scan = self.invoke([self.target+9000])
        sleep.assert_not_called()
        self.assertEqual(status, "no_candidate")

    def test_missed_minute_cannot_start_new_entry(self):
        status, sleep, scan = self.invoke([self.target+65_000])
        self.assertEqual(status, "outside_scheduled_minute")
        scan.assert_not_called()

    def test_exchange_clock_still_before_close(self):
        status, _, scan = self.invoke([self.target-1000, self.target-20])
        self.assertEqual(status, "outside_scheduled_minute")
        scan.assert_not_called()
