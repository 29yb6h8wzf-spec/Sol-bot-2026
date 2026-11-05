"""Download Binance Vision *public historical* ZIP + checksum, read-only.

No trading endpoints, credentials, Binance SDK or account access.
Download is opt-in by explicit function invocation; never on import.
"""
from datetime import date as Date, timedelta
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from .offline_binance_archive_verify import verify_binance_archive

BASE = "https://data.binance.vision/data/futures/um/daily/klines"
SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}
MAX_ZIP_BYTES = 4_000_000
MAX_CHECKSUM_BYTES = 512

def download_daily_public_archive(*, symbol, day, directory, today_utc=None):
    if symbol not in SYMBOLS:
        raise ValueError("unsupported_symbol")
    try:
        d = Date.fromisoformat(day)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_day") from exc
    if d.isoformat() != day:
        raise ValueError("invalid_day")
    now = today_utc or Date.today()
    if type(now) is not Date or d >= now:
        raise ValueError("archive_not_complete_day")
    filename = f"{symbol}-5m-{day}.zip"
    prefix = f"{BASE}/{symbol}/5m/{filename}"
    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / filename
    checksum_path = dest / (filename + ".CHECKSUM")
    # Avoid leaving a stale archive that appears verified after a failure.
    for p in (zip_path, checksum_path):
        if p.exists():
            raise ValueError("archive_already_exists")
    def fetch(url, max_bytes):
        with urlopen(url, timeout=20) as response:
            # Reject redirects to other origins. urllib may follow them.
            if response.geturl().split("/")[2] != "data.binance.vision":
                raise ValueError("untrusted_redirect")
            payload = response.read(max_bytes + 1)
        if not payload or len(payload) > max_bytes:
            raise ValueError("invalid_download_size")
        return payload
    try:
        checksum = fetch(prefix + ".CHECKSUM", MAX_CHECKSUM_BYTES)
        archive = fetch(prefix, MAX_ZIP_BYTES)
        checksum_path.write_bytes(checksum)
        zip_path.write_bytes(archive)
        result = verify_binance_archive(zip_path, checksum_path,
                                        symbol=symbol, date=day)
    except Exception:
        zip_path.unlink(missing_ok=True)
        checksum_path.unlink(missing_ok=True)
        raise
    return {"zip_path": str(zip_path), "checksum_path": str(checksum_path),
            "archive_sha256": result["archive_sha256"],
            "checksum_matched": True,
            "download_host": "data.binance.vision",
            "source": "BINANCE_VISION_PUBLIC_ARCHIVE",
            "orders_sent": False}
