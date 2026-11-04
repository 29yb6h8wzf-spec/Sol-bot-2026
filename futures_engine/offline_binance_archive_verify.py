"""Verify a manually downloaded Binance public-data ZIP against its CHECKSUM.

No network, API keys, order routes, or exchange execution. Verification is
limited to integrity against a trusted checksum file; it is not a proof of
authenticity unless the checksum's origin is independently established.
"""
import hashlib
import re
import zipfile
from pathlib import Path

_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}
_MAX_UNCOMPRESSED = 10_000_000

def verify_binance_archive(zip_path, checksum_path, *, symbol, date, period="daily"):
    if symbol not in _SYMBOLS or period not in ("daily", "monthly"):
        raise ValueError("unsupported_archive")
    if not isinstance(date, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}" if period == "daily" else r"\d{4}-\d{2}", date):
        raise ValueError("invalid_archive_date")
    name = f"{symbol}-5m-{date}.zip"
    zpath, cpath = Path(zip_path), Path(checksum_path)
    if zpath.name != name or cpath.name != name + ".CHECKSUM":
        raise ValueError("unexpected_archive_filename")
    lines = cpath.read_text(encoding="utf-8").strip().splitlines()
    if len(lines) != 1:
        raise ValueError("invalid_checksum_file")
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^/\\\s]+)", lines[0].strip())
    if not match or match.group(2) != name:
        raise ValueError("checksum_filename_mismatch")
    digest = hashlib.sha256()
    with zpath.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != match.group(1).lower():
        raise ValueError("archive_checksum_mismatch")
    with zipfile.ZipFile(zpath) as archive:
        files = archive.infolist()
        if len(files) != 1 or files[0].filename != name[:-4] + ".csv":
            raise ValueError("unexpected_zip_members")
        member = files[0]
        if member.file_size > _MAX_UNCOMPRESSED or member.is_dir():
            raise ValueError("archive_too_large")
        # Do not extract ZIP members to disk: prevents traversal and zip bombs.
        with archive.open(member) as f:
            csv_bytes = f.read(_MAX_UNCOMPRESSED + 1)
        if len(csv_bytes) > _MAX_UNCOMPRESSED:
            raise ValueError("archive_too_large")
    return {"archive_sha256": digest.hexdigest(), "csv_bytes": csv_bytes,
            "symbol": symbol, "interval": "5m", "period": period, "date": date,
            "checksum_matched": True,
            "checksum_origin_independently_verified": False,
            "orders_sent": False}
