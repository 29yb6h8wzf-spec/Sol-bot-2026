import hashlib
import hmac
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import binance_permissions as probe


class PermissionsTest(unittest.TestCase):
    def simulate(self, responses):
        def connect(host, **kwargs):
            conn = Mock()
            def request(method, target, headers):
                path, params = target.split("?")
                expected_path, status, body = responses[host]
                self.assertEqual((method, path), ("GET", expected_path))
                query, signature = params.split("&signature=")
                self.assertEqual(query, "timestamp=1000&recvWindow=5000")
                self.assertEqual(signature, hmac.new(b"sample-secret", query.encode(), hashlib.sha256).hexdigest())
                self.assertEqual(headers, {"X-MBX-APIKEY": "sample-key"})
                response = io.BytesIO(body)
                response.status = status
                conn.getresponse.return_value = response
            conn.request.side_effect = request
            return conn
        with patch.dict(os.environ, {"BINANCE_CREDENTIALS_JSON": json.dumps({
            "API_KEY": "sample-key", "API_SECRET": "sample-secret"})}, clear=True), \
             patch.object(probe.time, "time_ns", return_value=1000000000), \
             patch.object(probe.http.client, "HTTPSConnection", side_effect=connect) as factory:
            result, code = probe.run()
            self.assertEqual(factory.call_count, 2)
            self.assertNotIn("sample-", json.dumps(result))
            return result, code

    def pair(self, key=b'{"enableFutures": true}', account=b'{"canTrade": true}', status=200):
        return {"api.binance.com": ("/sapi/v1/account/apiRestrictions", 200, key),
                "fapi.binance.com": ("/fapi/v1/accountConfig", status, account)}

    def test_enabled(self):
        self.assertEqual(self.simulate(self.pair())[1], 0)

    def test_denied_key(self):
        self.assertEqual(self.simulate(self.pair(key=b'{"enableFutures":false}'))[1], 1)

    def test_denied_account(self):
        self.assertEqual(self.simulate(self.pair(account=b'{"canTrade":false}'))[1], 1)

    def test_requires_boolean(self):
        for body in (b'{}', b'{"canTrade":"true"}', b'{"canTrade":1}', b'invalid'):
            with self.subTest(body=body):
                self.assertEqual(self.simulate(self.pair(account=body))[1], 2)

    def test_redacts_errors(self):
        result, code = self.simulate(self.pair(account=b'{"code":-2015,"msg":"sample-private"}', status=401))
        self.assertEqual(code, 2)
        self.assertEqual(result["checks"]["canTrade"], {"http_status":401, "binance_code":-2015})

    def test_redirect_not_followed(self):
        self.assertEqual(self.simulate(self.pair(status=302))[1], 2)

    def test_missing_credentials(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(probe.http.client, "HTTPSConnection") as factory:
            self.assertEqual(probe.run()[1], 2)
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
