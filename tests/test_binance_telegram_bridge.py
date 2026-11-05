"""Offline fail-closed tests; never send HTTP or orders."""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# The production research outbox/preview live on AWS and are intentionally
# not part of this standalone CI unit-test fixture. Inject inert test stubs.
import sys
import types
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import futures_engine  # Preserve the real package for other collected tests.
outbox_stub = types.ModuleType("futures_engine.research_outbox")
outbox_stub.DB = "/unused-ci-research.sqlite3"
preview_stub = types.ModuleType("futures_engine.research_sqs_preview")
def _no_live_preview(*args, **kwargs):
    raise RuntimeError("offline_preview_stub_must_be_mocked")
preview_stub.preview = _no_live_preview
sys.modules["futures_engine.research_outbox"] = outbox_stub
sys.modules["futures_engine.research_sqs_preview"] = preview_stub

from binance_telegram_bridge import (
    ENABLE_VAR, check_endpoint, load_secret, load_ssm_secret, publish, sign_payload,
)

URL = "https://sol-bot-2026.29yb6h8wzf.workers.dev/internal/binance-research"


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "research.sqlite3"
        self.secret = Path(self.tmp.name) / "secret"
        self.secret.write_bytes(b"test-only-bridge-secret-32-bytes-abcdefgh")
        self.secret.chmod(0o600)
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE research_outbox ("
                       "signal_id TEXT PRIMARY KEY, symbol TEXT, candle_ms INTEGER,"
                       "state TEXT, payload TEXT)")
            db.execute("INSERT INTO research_outbox VALUES (?,?,?,?,?)",
                       ("research-test", "SOL/USDT:USDT", 1793724000000,
                        "PENDING_REVIEW", "{}"))
        self.env = patch.dict(os.environ, {ENABLE_VAR: "1"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.preview = patch(
            "binance_telegram_bridge.preview",
            return_value={"payload": {
                "signal_id": "r-0123456789abcdef01234567",
                "symbol": "SOLUSDT", "direction": "long", "score": 85,
                "timestamp": 1793724300, "source": "verified_85_score_engine"}})
        self.preview.start()
        self.addCleanup(self.preview.stop)

    def run_publish(self, transport, now=1793724330):
        return publish(db=str(self.db), url=URL, secret_path=self.secret,
                       now=now, transport=transport)

    def test_valid_owner_only_payload(self):
        sent = []
        def transport(url, raw, ts, signature):
            sent.append((url, json.loads(raw), ts, signature))
            return True
        result = self.run_publish(transport)
        self.assertEqual(result["delivered"], 1)
        self.assertFalse(result["orders_sent"])
        self.assertEqual(sent[0][0], URL)
        self.assertEqual(sent[0][1]["score"], 85)
        self.assertFalse(sent[0][1]["execution_authorized"])
        self.assertEqual(len(sent[0][3]), 64)

    def test_duplicate_never_resent(self):
        calls = []
        self.run_publish(lambda *args: calls.append(args) or True)
        self.run_publish(lambda *args: calls.append(args) or True)
        self.assertEqual(len(calls), 1)

    def test_failure_is_unconfirmed_no_retry(self):
        def fail(*args):
            raise TimeoutError("ambiguous")
        result = self.run_publish(fail)
        self.assertEqual(result["send_failed_unconfirmed"], 1)
        self.assertEqual(self.run_publish(lambda *args: True)["delivered"], 0)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute(
                "SELECT status FROM binance_telegram_delivery").fetchone()[0],
                "UNCONFIRMED")

    def test_false_acknowledgement_fails_closed(self):
        self.assertEqual(self.run_publish(lambda *args: False)["delivered"], 0)

    def test_disabled_by_default(self):
        os.environ.pop(ENABLE_VAR, None)
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            self.run_publish(lambda *args: True)

    def test_reject_other_worker(self):
        with self.assertRaisesRegex(ValueError, "invalid_cloudflare"):
            check_endpoint("https://attacker.workers.dev/internal/binance-research")

    def test_reject_http(self):
        with self.assertRaises(ValueError):
            check_endpoint(URL.replace("https:", "http:"))

    def test_reject_query(self):
        with self.assertRaises(ValueError):
            check_endpoint(URL + "?secret=abc")

    def test_reject_world_readable_secret(self):
        self.secret.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "permissions"):
            load_secret(self.secret)

    def test_reject_symlink_secret(self):
        link = Path(self.tmp.name) / "link"
        link.symlink_to(self.secret)
        with self.assertRaisesRegex(ValueError, "permissions"):
            load_secret(link)

    def test_reject_short_secret(self):
        self.secret.write_bytes(b"short")
        with self.assertRaisesRegex(ValueError, "invalid_bridge_secret"):
            load_secret(self.secret)

    def test_ssm_iam_role_secure_parameter(self):
        calls = []
        class FakeSSM:
            def get_parameter(self, **kwargs):
                calls.append(kwargs)
                return {"Parameter": {"Value": "a" * 64}}
        fake = types.ModuleType("boto3")
        fake.client = lambda service, region_name: FakeSSM()
        with patch.dict(sys.modules, {"boto3": fake}):
            self.assertEqual(load_ssm_secret(), b"a" * 64)
            self.assertTrue(calls[0]["WithDecryption"])

    def test_ssm_invalid_secret_fails_closed(self):
        class FakeSSM:
            def get_parameter(self, **kwargs):
                return {"Parameter": {"Value": "short"}}
        fake = types.ModuleType("boto3")
        fake.client = lambda service, region_name: FakeSSM()
        with patch.dict(sys.modules, {"boto3": fake}):
            with self.assertRaisesRegex(ValueError, "invalid_ssm_bridge_secret"):
                load_ssm_secret()

    def test_hmac_matches_expected(self):
        payload = {"type": "test", "score": 85}
        raw, sig = sign_payload(payload, b"abc", 123)
        expected = hmac.new(b"abc", b"123." + raw, hashlib.sha256).hexdigest()
        self.assertEqual(sig, expected)

    def test_old_candidate_skipped(self):
        self.preview.stop()
        with patch("binance_telegram_bridge.preview", side_effect=ValueError("expired")):
            self.assertEqual(self.run_publish(lambda *args: True)["expired"], 1)
        self.preview.start()


if __name__ == "__main__":
    unittest.main()
