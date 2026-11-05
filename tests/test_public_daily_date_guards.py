"""Date binding checks for public archive replay."""
import hashlib
import zipfile
import pytest
from futures_engine import public_daily_replay as module

T = 1793738100000
NAME = "SOLUSDT-5m-2026-11-03.zip"

def p(**changes):
    x = dict(signal_id="date-guard", symbol="SOLUSDT",
             status="INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE",
             orders_sent=False, execution_authorized=False,
             risk_snapshot_approved=False, side="long",
             entry="100", stop="99", target="102", quantity="1",
             closed_5m_candle_ms=T)
    x.update(changes)
    return x

def make_archive(tmp_path, candle):
    z = tmp_path/NAME
    with zipfile.ZipFile(z,"w") as f:
        f.writestr(NAME[:-4]+".csv", f"{candle},100,102.5,99.8,102\n")
    c = tmp_path/(NAME+".CHECKSUM")
    c.write_text(hashlib.sha256(z.read_bytes()).hexdigest()+"  "+NAME+"\n")
    return z,c

def test_signal_day_mismatch_rejected_before_download(monkeypatch,tmp_path):
    def fail(**kw):
        raise AssertionError("download must not be called")
    monkeypatch.setattr(module,"download_daily_public_archive",fail)
    with pytest.raises(ValueError,match="signal_outside_archive_day"):
        module.run_public_daily_replay(
            plan=p(closed_5m_candle_ms=T+86400000),
            symbol="SOLUSDT",day="2026-11-03",
            directory=tmp_path,journal_path=tmp_path/"j.sqlite3")

def test_csv_candle_day_mismatch_rejected(monkeypatch,tmp_path):
    z,c=make_archive(tmp_path,T+86400000)
    monkeypatch.setattr(module,"download_daily_public_archive",
        lambda **kw: {"zip_path":str(z),"checksum_path":str(c)})
    with pytest.raises(ValueError,match="candle_outside_archive_day"):
        module.run_public_daily_replay(
            plan=p(),symbol="SOLUSDT",day="2026-11-03",
            directory=tmp_path,journal_path=tmp_path/"j.sqlite3")
