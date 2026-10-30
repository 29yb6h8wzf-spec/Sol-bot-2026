"""Offline testnet probe tests: no network calls or exchange orders."""
import unittest

from futures_engine.testnet_probe import PUBLIC_PATHS, TESTNET_BASE_URL, probe_public_endpoints


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return self.body[:size]


class ProbeTests(unittest.TestCase):
    def test_only_fixed_public_get_paths_are_called(self):
        seen = []

        def opener(req, timeout):
            seen.append((req.full_url, req.get_method(), timeout, dict(req.header_items())))
            body = b'{}' if req.full_url.endswith('/ping') else b'{"serverTime": 123}'
            return FakeResponse(body)

        results = probe_public_endpoints(opener=opener)
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual([item[0] for item in seen], [TESTNET_BASE_URL + p for p in PUBLIC_PATHS])
        self.assertTrue(all(item[1] == 'GET' for item in seen))
        self.assertTrue(all('Authorization' not in item[3] and 'X-Mbx-Apikey' not in item[3] for item in seen))

    def test_bad_payload_fails_closed(self):
        results = probe_public_endpoints(opener=lambda req, timeout: FakeResponse(b'{"bad":true}'))
        self.assertFalse(all(r.ok for r in results))

    def test_network_failure_fails_closed(self):
        def fail(req, timeout):
            raise OSError('connection refused')
        results = probe_public_endpoints(opener=fail)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(not r.ok and r.detail == 'OSError' for r in results))

    def test_oversize_fails_closed(self):
        results = probe_public_endpoints(opener=lambda req, timeout: FakeResponse(b' ' * 4097))
        self.assertTrue(all(not r.ok for r in results))

    def test_non_200_fails_closed(self):
        results = probe_public_endpoints(opener=lambda req, timeout: FakeResponse(b'{}', 403))
        self.assertTrue(all(not r.ok for r in results))


if __name__ == '__main__':
    unittest.main()
