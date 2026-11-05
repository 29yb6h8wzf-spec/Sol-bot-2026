"""Mocked public archive downloads; never access the network in CI."""
import hashlib
import io
import zipfile
from datetime import date
import pytest
from futures_engine import public_archive_download as mod

DAY = "2026-11-02"
NAME = f"SOLUSDT-5m-{DAY}.zip"

def payload():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(NAME[:-4] + ".csv", "1793577600000,100,101,99,100\n")
    zipped = buf.getvalue()
    checksum = f"{hashlib.sha256(zipped).hexdigest()}  {NAME}\n".encode()
    return zipped, checksum

class FakeResponse:
    def __init__(self, url, data):
        self.url, self.data = url, data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def geturl(self):
        return self.url
    def read(self, size):
        return self.data[:size]

def test_download_and_verify(monkeypatch, tmp_path):
    zipped, checksum = payload()
    def fake(url, timeout):
        return FakeResponse(url, checksum if url.endswith(".CHECKSUM") else zipped)
    monkeypatch.setattr(mod, "urlopen", fake)
    result = mod.download_daily_public_archive(
        symbol="SOLUSDT", day=DAY, directory=tmp_path,
        today_utc=date(2026,11,4))
    assert result["checksum_matched"] is True
    assert result["orders_sent"] is False

def test_mismatch_cleans_files(monkeypatch, tmp_path):
    zipped, checksum = payload()
    def fake(url, timeout):
        return FakeResponse(url, b"0"*64+b"  "+NAME.encode()+b"\n"
                            if url.endswith(".CHECKSUM") else zipped)
    monkeypatch.setattr(mod, "urlopen", fake)
    with pytest.raises(ValueError, match="checksum"):
        mod.download_daily_public_archive(
            symbol="SOLUSDT", day=DAY, directory=tmp_path,
            today_utc=date(2026,11,4))
    assert not list(tmp_path.iterdir())

def test_future_day_blocked_without_network(tmp_path):
    with pytest.raises(ValueError, match="complete_day"):
        mod.download_daily_public_archive(
            symbol="SOLUSDT", day="2026-11-04", directory=tmp_path,
            today_utc=date(2026,11,4))

def test_unsupported_symbol_blocked(tmp_path):
    with pytest.raises(ValueError, match="symbol"):
        mod.download_daily_public_archive(
            symbol="ADAUSDT", day=DAY, directory=tmp_path,
            today_utc=date(2026,11,4))
