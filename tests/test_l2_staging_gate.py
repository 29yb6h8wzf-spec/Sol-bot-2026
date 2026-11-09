"""Offline regression for staging REST fail-closed gate."""
import json
from contextlib import contextmanager

import pytest

from research import public_market_staging as probe


def test_rest_gate_rejects_partial_provider_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(probe, "DURATION_SECONDS", 0.01)
    monkeypatch.setattr(probe, "INTERVAL_SECONDS", 0)

    @contextmanager
    def fake_urlopen(request, timeout):
        if "okx.com" not in request.full_url:
            raise probe.urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
        class Response:
            def read(self, *args):
                return json.dumps({"data": [{"bids": [["100", "1"]], "asks": [["101", "1"]]}]}).encode()
        yield Response()

    monkeypatch.setattr(probe.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="missing successful data"):
        probe.run()
    report = json.loads((tmp_path / "staging-results/public-market-720s.json").read_text())
    assert report["streams"]["okx_SOL"]["success"] > 0
    assert report["streams"]["bybit_SOL"]["success"] == 0
