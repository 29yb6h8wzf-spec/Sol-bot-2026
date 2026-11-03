"""Offline tests for demo monitor preflight guard; no exchange calls."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from demo_risk_adapter import preflight_with_monitor

NOW = 1793719000


def intent():
    return {"symbol": "XRP/USDT:USDT", "side": "long",
            "source": "verified_85_score_engine", "score": 90,
            "entry": "2", "stop": "1.9", "target": "2.2", "quantity": "10"}


def account():
    return {"equity": "150", "day_start": "150", "used_margin": "0",
            "open_risk": "0", "leverage": 2}


class MonitorGuardTests(unittest.TestCase):
    def test_missing_monitor_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(preflight_with_monitor(intent(), account(),
                status_path=Path(folder) / "missing", now=NOW)[0], False)

    @unittest.skipUnless(os.geteuid() == 0, "requires root-owned snapshot")
    def test_blocked_monitor_overrides_valid_offline_intent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            path.write_text(json.dumps({
                "status": "BLOCKED", "reason": "ALLOCATION_LEDGER_NOT_RECONCILED",
                "observed_at": NOW, "allocation_ledger_reconciled": False,
                "execution_authorized": False}))
            path.chmod(0o600)
            self.assertEqual(preflight_with_monitor(intent(), account(),
                status_path=path, now=NOW), (False, "risk_monitor_blocked"))
            self.assertEqual(preflight_with_monitor(intent(), account(),
                status_path=path, now=NOW+91)[1], "risk_monitor_status_stale")
            path.chmod(0o644)
            self.assertEqual(preflight_with_monitor(intent(), account(),
                status_path=path, now=NOW)[1], "risk_monitor_status_untrusted")

if __name__ == "__main__":
    unittest.main()
