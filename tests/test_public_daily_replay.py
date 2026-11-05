"""Synthetic end-to-end archive test; no network or orders."""
import hashlib
import zipfile
import pytest
from futures_engine import public_daily_replay as module

T = 1793738100000
NAME = "SOLUSDT-5m-2026-11-03.zip"

def archive(tmp_path, rows):
    z = tmp_path / NAME
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(NAME[:-4] + ".csv", rows)
    c = tmp_path / (NAME + ".CHECKSUM")
    c.write_text(hashlib.sha256(z.read_bytes()).hexdigest() + "  " + NAME + "\n")
    return z,c

def plan():
    return dict(signal_id="archive-synthetic",symbol="SOLUSDT",
                status="INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
                orders_sent=False,execution_authorized=False,
                risk_snapshot_approved=False,side="long",
                entry="100",stop="99",target="102",quantity="1",
                closed_5m_candle_ms=T)

def test_public_archive_pipeline(monkeypatch,tmp_path):
    z,c = archive(tmp_path, f"{T},100,102.5,99.8,102,100\n")
    monkeypatch.setattr(module, "download_daily_public_archive",
        lambda **kw: {"zip_path":str(z),"checksum_path":str(c)})
    a = module.run_public_daily_replay(
        plan=plan(),symbol="SOLUSDT",day="2026-11-03",
        directory=tmp_path,journal_path=tmp_path/"journal.sqlite3")
    assert a["summary"]["closed_hypothetical"] == 1
    assert a["archive_checksum_matched"] is True
    assert a["archive_checksum_origin_independently_verified"] is False
    assert a["orders_sent"] is False

def test_archive_missing_signal_rejected(monkeypatch,tmp_path):
    z,c = archive(tmp_path, f"{T-300000},100,101,99.5,100,100\n")
    monkeypatch.setattr(module, "download_daily_public_archive",
        lambda **kw: {"zip_path":str(z),"checksum_path":str(c)})
    with pytest.raises(ValueError,match="signal_not_in_archive"):
        module.run_public_daily_replay(
            plan=plan(),symbol="SOLUSDT",day="2026-11-03",
            directory=tmp_path,journal_path=tmp_path/"journal.sqlite3")
