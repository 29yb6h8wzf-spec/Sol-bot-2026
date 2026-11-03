"""Fail-closed, owner-only HTTPS delivery of verified Binance research to Cloudflare.

DISABLED by default. No exchange API, no order placement, no Telegram token.
Unknown network outcomes are never automatically retried (manual reconciliation).
"""
import hashlib
import hmac
import json
import os
import sqlite3
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from futures_engine.research_outbox import DB
from futures_engine.research_sqs_preview import preview

SECRET_PATH = Path("/etc/signalpilot/binance-research-bridge-secret")
URL_VAR = "SIGNALPILOT_BINANCE_RESEARCH_URL"
ENABLE_VAR = "SIGNALPILOT_BINANCE_TELEGRAM_ENABLED"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_endpoint(url):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or
            parsed.hostname != "sol-bot-2026.29yb6h8wzf.workers.dev" or parsed.port not in (None, 443) or
            parsed.path != "/internal/binance-research" or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("invalid_cloudflare_ingest_endpoint")
    return url


def load_secret(path=SECRET_PATH):
    path = Path(path)
    st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or
            st.st_mode & 0o077):
        raise ValueError("untrusted_bridge_secret_permissions")
    secret = path.read_bytes().strip()
    if len(secret) < 32 or len(secret) > 256:
        raise ValueError("invalid_bridge_secret")
    return secret


def sign_payload(body, secret, timestamp):
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret, str(timestamp).encode() + b"." + raw,
                         hashlib.sha256).hexdigest()
    return raw, signature


def send_https(url, raw, timestamp, signature):
    req = urllib.request.Request(
        url, data=raw, method="POST",
        headers={"Content-Type": "application/json",
                 "X-Signalpilot-Timestamp": str(timestamp),
                 "X-Signalpilot-Signature": signature})
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(req, timeout=8) as response:
        if response.status != 200:
            raise RuntimeError("research_delivery_http_error")
        payload = response.read(2048)
        result = json.loads(payload)
        if result.get("status") != "delivered_owner_only" or result.get("research_only") is not True:
            raise RuntimeError("research_delivery_unconfirmed")
        return True


def publish(*, db=DB, url=None, secret_path=SECRET_PATH, now=None, transport=send_https):
    if os.environ.get(ENABLE_VAR) != "1":
        raise RuntimeError("binance_research_telegram_disabled")
    url = check_endpoint(url or os.environ.get(URL_VAR, ""))
    secret = load_secret(secret_path)
    now = int(time.time()) if now is None else int(now)
    stats = {"delivered": 0, "expired": 0, "claimed_or_unconfirmed": 0,
             "send_failed_unconfirmed": 0, "orders_sent": False}
    with sqlite3.connect(db, timeout=20) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS binance_telegram_delivery ("
            "signal_id TEXT PRIMARY KEY, status TEXT NOT NULL, "
            "attempted_at INTEGER NOT NULL)")
        rows = conn.execute(
            "SELECT signal_id,symbol,candle_ms,state,payload "
            "FROM research_outbox ORDER BY candle_ms DESC LIMIT 50").fetchall()
        for sid, symbol, candle, state, raw in rows:
            if conn.execute("SELECT 1 FROM binance_telegram_delivery WHERE signal_id=?",
                            (sid,)).fetchone():
                stats["claimed_or_unconfirmed"] += 1
                continue
            record = {"signal_id": sid, "symbol": symbol, "candle_ms": candle,
                      "state": state, "payload": json.loads(raw)}
            try:
                checked = preview(record, now=now)
            except ValueError:
                stats["expired"] += 1
                continue
            p = checked["payload"]
            body = {
                "type": "SIGNALPILOT_BINANCE_RESEARCH_V1",
                "signal_id": p["signal_id"],
                "symbol": p["symbol"],
                "direction": p["direction"],
                "score": p["score"],
                "timestamp": p["timestamp"],
                "source": p["source"],
                "execution_authorized": False,
                "orders_sent": False,
            }
            raw_body, signature = sign_payload(body, secret, now)
            # Claim durably before any network call; never resend an ambiguous result.
            conn.execute("INSERT INTO binance_telegram_delivery VALUES (?,?,?)",
                         (sid, "UNCONFIRMED", now))
            conn.commit()
            try:
                if transport(url, raw_body, now, signature) is not True:
                    raise RuntimeError("research_delivery_not_acknowledged")
            except Exception:
                stats["send_failed_unconfirmed"] += 1
                continue
            conn.execute("UPDATE binance_telegram_delivery SET status=? WHERE signal_id=?",
                         ("DELIVERED_OWNER_ONLY", sid))
            conn.commit()
            stats["delivered"] += 1
    return stats


if __name__ == "__main__":
    print(json.dumps(publish(), sort_keys=True))
