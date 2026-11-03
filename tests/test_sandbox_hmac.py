import unittest

from futures_engine.sandbox_hmac import sign, verify

KEY = b"a" * 32
OTHER = b"b" * 32
ENVELOPE = {"type": "SIGNALPILOT_SANDBOX_RESEARCH",
            "research_signal_id": "research-test",
            "candidate": {"symbol": "BTCUSDT", "score": 85},
            "execution_authorized": False, "orders_enabled": False}


class SandboxHMACTests(unittest.TestCase):
    def test_round_trip(self):
        signed = sign(ENVELOPE, secret=KEY, now=1000)
        self.assertEqual(verify(signed, secret=KEY, now=1001), ENVELOPE)

    def test_tampering(self):
        signed = sign(ENVELOPE, secret=KEY, now=1000)
        signed["candidate"]["score"] = 95
        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            verify(signed, secret=KEY, now=1001)

    def test_wrong_key(self):
        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            verify(sign(ENVELOPE, secret=KEY, now=1000),
                   secret=OTHER, now=1001)

    def test_expired(self):
        with self.assertRaisesRegex(ValueError, "expired"):
            verify(sign(ENVELOPE, secret=KEY, now=1000),
                   secret=KEY, now=1121)

    def test_missing(self):
        with self.assertRaises(ValueError):
            verify(ENVELOPE, secret=KEY, now=1000)

    def test_short_key(self):
        with self.assertRaises(ValueError):
            sign(ENVELOPE, secret=b"weak", now=1000)


if __name__ == "__main__":
    unittest.main()
