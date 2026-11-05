"""Read-only SignalPilot infrastructure health audit; no exchange orders."""
from pathlib import Path
from datetime import datetime, timezone
import json
import sqlite3
import subprocess
import time

ROOT = Path("/opt/signalpilot")
COINS = ("btc", "eth", "sol", "xrp")
UNITS = [f"signalpilot-paper-{coin}.timer" for coin in COINS] + [
    "signalpilot-signal-decision.timer",
    "signalpilot-sqs-consumer.service",
    "signalpilot-signal-inbox.service",
]

def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=10)

def check():
    checks = {}
    for unit in UNITS:
        proc = run("systemctl", "is-active", unit)
        checks[unit] = {"ok": proc.returncode == 0 and proc.stdout.strip() == "active", "state": proc.stdout.strip()}
    for coin in COINS:
        unit = f"signalpilot-paper-{coin}.service"
        proc = run("systemctl", "show", unit, "--property=Result,ExecMainStatus,InactiveExitTimestamp")
        props = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
        logs = run("journalctl", "-u", unit, "--since", "20 minutes ago", "--no-pager", "--output=cat")
        completed = logs.stdout.count("Finished signalpilot-paper-")
        checks[unit] = {
            "ok": proc.returncode == 0 and props.get("Result") == "success" and props.get("ExecMainStatus") == "0" and completed > 0,
            "result": props.get("Result"), "exit_status": props.get("ExecMainStatus"),
            "last_start": props.get("InactiveExitTimestamp"), "completed_last_20m": completed,
        }
        try:
            state = json.loads((ROOT / f"paper-ledger-{coin}.json").read_text())
            checks[f"ledger:{coin}"] = {
                "ok": isinstance(state.get("history"), list) and "equity" in state,
                "equity": state.get("equity"), "history_count": len(state.get("history", [])),
            }
        except (OSError, ValueError, TypeError) as exc:
            checks[f"ledger:{coin}"] = {"ok": False, "error": type(exc).__name__}
    try:
        with sqlite3.connect("file:/opt/signalpilot/signal-inbox.sqlite3?mode=ro", uri=True, timeout=3) as db:
            count, last = db.execute("SELECT COUNT(*), MAX(received_at) FROM signals").fetchone()
            checks["inbox"] = {"ok": True, "count": count, "last_received_at": last}
    except (sqlite3.Error, OSError) as exc:
        checks["inbox"] = {"ok": False, "error": type(exc).__name__}
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "healthy" if all(item["ok"] for item in checks.values()) else "degraded",
        "mode": "paper", "checks": checks,
    }

if __name__ == "__main__":
    report = check()
    tmp = ROOT / "signalpilot-health.json.tmp"
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    tmp.replace(ROOT / "signalpilot-health.json")
    print(json.dumps({"status": report["status"], "failed": [key for key, value in report["checks"].items() if not value["ok"]], "checked_at_utc": report["checked_at_utc"]}))
    raise SystemExit(0 if report["status"] == "healthy" else 2)
