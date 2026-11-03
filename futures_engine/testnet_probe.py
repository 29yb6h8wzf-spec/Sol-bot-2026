"""Opt-in public Binance USD-M Futures testnet connectivity check.

Never reads API credentials, authenticates, or places/cancels orders.
This module is not imported by the live Cloudflare Worker.
"""
import json
import urllib.request
from dataclasses import dataclass

TESTNET_BASE_URL = 'https://testnet.binancefuture.com'
PUBLIC_PATHS = ('/fapi/v1/ping', '/fapi/v1/time')


@dataclass(frozen=True)
class ProbeResult:
    endpoint: str
    ok: bool
    detail: str


def probe_public_endpoints(opener=None, timeout=8):
    """Read only two fixed public endpoints; fail closed on malformed responses."""
    if opener is None:
        opener = urllib.request.urlopen
    results = []
    for path in PUBLIC_PATHS:
        req = urllib.request.Request(
            TESTNET_BASE_URL + path,
            headers={'User-Agent': 'SignalPilot-Testnet-Public-Probe/1.0'},
            method='GET',
        )
        try:
            with opener(req, timeout=timeout) as response:
                if response.status != 200:
                    raise ValueError('unexpected HTTP status')
                raw = response.read(4097)
                if len(raw) > 4096:
                    raise ValueError('oversized response')
                payload = json.loads(raw)
                if path.endswith('/ping') and payload != {}:
                    raise ValueError('unexpected ping payload')
                if path.endswith('/time') and (
                    not isinstance(payload, dict)
                    or type(payload.get('serverTime')) is not int
                    or payload['serverTime'] <= 0
                ):
                    raise ValueError('invalid server time')
            results.append(ProbeResult(path, True, 'public endpoint reachable'))
        except (OSError, ValueError, TimeoutError) as exc:
            # Do not print response bodies or secret values.
            results.append(ProbeResult(path, False, type(exc).__name__))
    return results


def main():
    results = probe_public_endpoints()
    print(json.dumps({
        'environment': 'binance-usdm-testnet',
        'public_only': True,
        'authenticated': False,
        'orders_submitted': 0,
        'results': [vars(r) for r in results],
    }))
    return 0 if all(r.ok for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
