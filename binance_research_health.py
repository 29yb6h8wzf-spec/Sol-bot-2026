"""Read-only Binance Futures research telemetry; no Telegram or exchange writes.

Summarizes verified 85+ research candidates and the sandbox-only handoff.
Never represents SQS delivery as Telegram delivery or as execution permission.
"""
import json
import os
import sqlite3
import tempfile
import time
from collections import Counter
from pathlib import Path

RESEARCH_DB = Path("/opt/signalpilot/research-history.sqlite3")
SANDBOX_DB = Path("/opt/signalpilot/sandbox-received.sqlite3")
OUTPUT = Path("/opt/signalpilot/binance-research-health.json")
SYMBOLS = {"BTC/USDT:USDT", "ETH/USDT:USDT",
           "SOL/USDT:USDT", "XRP/USDT:USDT"}


def _connect(path):
    if not Path(path).is_file():
        raise ValueError("research_database_missing")
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def _scalar(db, sql, params=()):
    return int(db.execute(sql, params).fetchone()[0])


def summarize(*, research_db=RESEARCH_DB, sandbox_db=SANDBOX_DB, now=None):
    now = int(time.time()) if now is None else int(now)
    cutoff = now - 86400
    counts = Counter()
    per_symbol = {s: {"scans": 0, "candidates_85_plus": 0,
                      "verification_rejected": 0, "errors": 0,
                      "latest_scan_at": None} for s in sorted(SYMBOLS)}
    latest = None
    with _connect(research_db) as db:
        rows = db.execute(
            "SELECT observed_at,symbol,status,payload FROM research_scans "
            "WHERE observed_at>=? AND observed_at<=? ORDER BY observed_at",
            (cutoff, now + 60)).fetchall()
        for observed_at, symbol, status, raw in rows:
            if symbol not in SYMBOLS:
                raise ValueError("unknown_research_symbol")
            payload = json.loads(raw)
            if (not isinstance(payload, dict) or
                    payload.get("symbol") != symbol or
                    payload.get("status") != status or
                    status not in ("RESEARCH_ONLY", "BLOCKED")):
                raise ValueError("invalid_research_record")
            bucket = per_symbol[symbol]
            bucket["scans"] += 1
            bucket["latest_scan_at"] = observed_at
            latest = max(latest or observed_at, observed_at)
            counts["scan_rows"] += 1
            if status == "BLOCKED":
                bucket["errors"] += 1
                counts["scan_errors"] += 1
                continue
            accepted = payload.get("candidates_85_plus")
            rejected = payload.get("rejected_candidates", [])
            if not isinstance(accepted, list) or not isinstance(rejected, list):
                raise ValueError("invalid_candidate_lists")
            for candidate in accepted:
                if (not isinstance(candidate, dict) or
                        type(candidate.get("score")) is not int or
                        candidate["score"] < 85 or candidate["score"] > 100):
                    raise ValueError("invalid_research_score")
            bucket["candidates_85_plus"] += len(accepted)
            bucket["verification_rejected"] += len(rejected)
            counts["candidates_85_plus"] += len(accepted)
            counts["verification_rejected"] += len(rejected)
        counts["outbox_total"] = _scalar(
            db, "SELECT COUNT(*) FROM research_outbox")
        counts["outbox_24h"] = _scalar(
            db, "SELECT COUNT(*) FROM research_outbox WHERE candle_ms>=?",
            (cutoff * 1000,))
        counts["sandbox_published_total"] = _scalar(
            db, "SELECT COUNT(*) FROM sandbox_publish_log "
            "WHERE message_id!='UNCONFIRMED'")
        counts["sandbox_unconfirmed_total"] = _scalar(
            db, "SELECT COUNT(*) FROM sandbox_publish_log "
            "WHERE message_id='UNCONFIRMED'")
    with _connect(sandbox_db) as db:
        counts["sandbox_received_total"] = _scalar(
            db, "SELECT COUNT(*) FROM sandbox_received")
    stale = latest is None or now - latest > 900
    status = "SCANNER_STALE" if stale else (
        "RESEARCH_ERRORS" if counts["scan_errors"] else "SCANNING")
    return {
        "source": "signalpilot_binance_futures_research_health_read_only",
        "observed_at": now,
        "window_seconds": 86400,
        "status": status,
        "scanner_stale": stale,
        "latest_scan_at": latest,
        "counts": dict(counts),
        "symbols": per_symbol,
        "telegram_delivery": "NOT_CONNECTED_FROM_AWS_RESEARCH",
        "sandbox_queue_is_not_telegram": True,
        "score_is_not_success_probability": True,
        "mode": "RESEARCH_ONLY",
        "execution_authorized": False,
        "orders_sent": False,
    }


def save(report, *, path=OUTPUT):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".research-health-", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    result = summarize()
    save(result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
