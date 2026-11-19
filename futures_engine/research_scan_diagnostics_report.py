"""Offline aggregation of research-only scan diagnostics; no execution access."""
from collections import Counter


def summarize_scan_diagnostics(results):
    """Count scans and setups separately; tolerate older scans without diagnostics."""
    totals = Counter()
    per_symbol = {}
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("invalid_scan_result")
        symbol = result.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("invalid_scan_symbol")
        bucket = per_symbol.setdefault(symbol, Counter())
        totals["scans"] += 1
        bucket["scans"] += 1
        if result.get("status") == "BLOCKED":
            totals["blocked_scans"] += 1
            bucket["blocked_scans"] += 1
        diagnostics = result.get("scan_diagnostics")
        if diagnostics is None:
            totals["legacy_scans_without_diagnostics"] += 1
            bucket["legacy_scans_without_diagnostics"] += 1
            continue
        if not isinstance(diagnostics, dict):
            raise ValueError("invalid_scan_diagnostics")
        keys = ("setups_seen", "below_threshold", "invalid_score",
                "verification_rejected", "eligible")
        if any(type(diagnostics.get(k)) is not int or diagnostics[k] < 0 for k in keys):
            raise ValueError("invalid_scan_counts")
        if sum(diagnostics[k] for k in keys[1:]) != diagnostics["setups_seen"]:
            raise ValueError("inconsistent_scan_counts")
        if type(diagnostics.get("no_setup")) is not bool or (
                diagnostics["no_setup"] != (diagnostics["setups_seen"] == 0)):
            raise ValueError("inconsistent_no_setup")
        totals["diagnosed_scans"] += 1
        bucket["diagnosed_scans"] += 1
        if diagnostics["no_setup"]:
            totals["no_setup_scans"] += 1
            bucket["no_setup_scans"] += 1
        for key in keys:
            totals[key] += diagnostics[key]
            bucket[key] += diagnostics[key]
    return {
        "totals": dict(sorted(totals.items())),
        "by_symbol": {symbol: dict(sorted(counts.items()))
                      for symbol, counts in sorted(per_symbol.items())},
        "execution_authorized": False,
    }
