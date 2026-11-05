"""Read-only SignalPilot research-staging release gate.

Reads a staging evidence JSON, current Git revisions and the Paper status
JSON. Never executes trade entrypoints, network clients, order methods,
systemctl mutations or deployment commands. It deliberately cannot authorize
Binance Demo/Live trading or make production changes.
"""
import argparse
import json
import subprocess
from pathlib import Path


REQUIRED_STAGING_MODE = "RESEARCH_STAGING_ONLY_NO_EXECUTION"
HISTORY_READY = "OHLCV_CONTINUITY_COMPLETE_PROVENANCE_UNAUTHENTICATED"


def _sha(repo):
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=15, check=True)
    sha = proc.stdout.strip()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("invalid_commit_sha")
    return sha


def _tracked_dirty(repo):
    # Exclude ephemeral untracked staging-results.json; do not inspect
    # secrets or describe untracked files.
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True, timeout=15, check=True)
    return bool(result.stdout.strip())


def _load(path):
    return json.loads(Path(path).read_text())


def check_release_gate(*, staging_dir, active_dir, expected_staging_sha,
                       evidence_path=None, paper_status_path=None):
    """Verify a read-only staging checkout; never return a live-ready signal.

    Use a versioned local baseline with exact full commit hash; a branch name
    or a user-provided staging JSON cannot override the deployed Git facts.
    """
    staging_dir = Path(staging_dir)
    active_dir = Path(active_dir)
    evidence_path = Path(evidence_path) if evidence_path else staging_dir / "staging-results.json"
    paper_status_path = (Path(paper_status_path) if paper_status_path
                         else active_dir / "binance-paper-status.json")
    problems = []
    try:
        observed_staging = _sha(staging_dir)
        observed_active = _sha(active_dir)
        dirty = _tracked_dirty(staging_dir)
        evidence = _load(evidence_path)
        paper_status = _load(paper_status_path)
        if not isinstance(evidence, dict) or not isinstance(paper_status, dict):
            raise ValueError("invalid_evidence_structure")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError):
        return {"status": "BLOCKED_RESEARCH_GATE", "reasons": ["missing_or_invalid_evidence"],
                "execution_authorized": False, "orders_sent": False,
                "production_ready": False}

    if (not isinstance(expected_staging_sha, str) or
            len(expected_staging_sha) != 40 or
            any(c not in "0123456789abcdef" for c in expected_staging_sha)):
        raise ValueError("invalid_expected_sha")
    if observed_staging != expected_staging_sha:
        problems.append("staging_commit_mismatch")
    if dirty:
        problems.append("staging_tracked_changes")
    if evidence.get("mode") != REQUIRED_STAGING_MODE:
        problems.append("incorrect_staging_mode")
    if evidence.get("staging_systemd_services_installed") is not False:
        problems.append("staging_services_not_isolated")
    if evidence.get("exchange_orders_sent") is not False:
        problems.append("staging_orders_not_verified_disabled")
    if evidence.get("source_branches_unmerged") is not True:
        problems.append("branch_review_scope_not_verified")
    if evidence.get("base_production_sha") != observed_active:
        problems.append("active_production_revision_changed")
    if paper_status.get("live_orders_enabled") is not False:
        problems.append("live_trading_not_verified_disabled")
    if evidence.get("verified_history_gate") != HISTORY_READY:
        problems.append("90_day_history_not_complete")
    # Even 90 days of self-declared data do not prove provenance, fees,
    # funding, out-of-sample expectancy, fills or protective order safety.
    problems.extend([
        "historical_source_authentication_not_proven",
        "funding_and_out_of_sample_profitability_not_proven",
        "exchange_execution_safety_not_approved",
    ])
    return {
        "status": "BLOCKED_RESEARCH_GATE",
        "reasons": problems,
        "staging_sha_match": observed_staging == expected_staging_sha,
        "active_production_sha_unchanged":
            evidence.get("base_production_sha") == observed_active,
        "staging_tracked_clean": not dirty,
        "offline_staging_checks_passed":
            not any(reason in problems for reason in (
                "staging_commit_mismatch", "staging_tracked_changes",
                "incorrect_staging_mode", "staging_services_not_isolated",
                "staging_orders_not_verified_disabled",
                "branch_review_scope_not_verified",
                "active_production_revision_changed",
                "live_trading_not_verified_disabled")),
        "execution_authorized": False,
        "orders_sent": False,
        "production_ready": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-dir", default="/opt/signalpilot-research-staging-20261105")
    parser.add_argument("--active-dir", default="/opt/signalpilot")
    parser.add_argument("--expected-staging-sha", required=True)
    parser.add_argument("--evidence-path")
    parser.add_argument("--paper-status-path")
    args = parser.parse_args(argv)
    result = check_release_gate(
        staging_dir=args.staging_dir, active_dir=args.active_dir,
        expected_staging_sha=args.expected_staging_sha,
        evidence_path=args.evidence_path,
        paper_status_path=args.paper_status_path)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["offline_staging_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
