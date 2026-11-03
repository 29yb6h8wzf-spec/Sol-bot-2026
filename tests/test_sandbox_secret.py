import base64
import unittest

from futures_engine.sandbox_secret import load_key


class FakeClient:
    def __init__(self, value):
        self.value = value

    def get_secret_value(self, **kwargs):
        assert kwargs["SecretId"] == "signalpilot/sandbox/hmac-v1"
        return {"SecretString": self.value}


class SandboxSecretTests(unittest.TestCase):
    def test_valid_base64(self):
        self.assertEqual(load_key(client=FakeClient(base64.b64encode(b"x"*32).decode())), b"x"*32)

    def test_wrong_length(self):
        with self.assertRaises(ValueError):
            load_key(client=FakeClient(base64.b64encode(b"x"*16).decode()))

    def test_invalid_base64(self):
        with self.assertRaises(ValueError):
            load_key(client=FakeClient("not-base64!"))


if __name__ == "__main__":
    unittest.main()
