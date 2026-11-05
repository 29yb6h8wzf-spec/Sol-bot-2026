"""Synthetic ZIP/CHECKSUM tests, no network."""
import hashlib
import zipfile
import pytest
from futures_engine.offline_binance_archive_verify import verify_binance_archive

NAME = "SOLUSDT-5m-2026-11-03.zip"

def archive(tmp_path, *, checksum_valid=True, member=None):
    z = tmp_path / NAME
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(member or NAME[:-4]+".csv",
                   "1793738100000,100,102,99,101,123\n")
    digest = hashlib.sha256(z.read_bytes()).hexdigest()
    c = tmp_path / (NAME + ".CHECKSUM")
    c.write_text(f"{digest if checksum_valid else '0'*64}  {NAME}\n")
    return z,c

def test_valid_integrity_but_origin_not_verified(tmp_path):
    z,c = archive(tmp_path)
    result = verify_binance_archive(z,c,symbol="SOLUSDT",date="2026-11-03")
    assert result["checksum_matched"] is True
    assert result["checksum_origin_independently_verified"] is False
    assert result["orders_sent"] is False

def test_corrupted_archive_blocked(tmp_path):
    z,c = archive(tmp_path, checksum_valid=False)
    with pytest.raises(ValueError, match="checksum_mismatch"):
        verify_binance_archive(z,c,symbol="SOLUSDT",date="2026-11-03")

def test_unexpected_zip_member_blocked(tmp_path):
    z,c = archive(tmp_path, member="../escape.csv")
    with pytest.raises(ValueError, match="unexpected_zip_members"):
        verify_binance_archive(z,c,symbol="SOLUSDT",date="2026-11-03")

def test_wrong_symbol_blocked(tmp_path):
    z,c = archive(tmp_path)
    with pytest.raises(ValueError):
        verify_binance_archive(z,c,symbol="BTCUSDT",date="2026-11-03")
