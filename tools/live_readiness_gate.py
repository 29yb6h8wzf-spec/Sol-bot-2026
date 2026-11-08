"""Read-only gate for progressing from Paper to Binance live execution.

No exchange credentials, orders, or changes to existing services.
Exit status 0 means evidence is complete, NOT permission to enable live trading.
"""
import argparse
import json
from pathlib import Path


def gate(evidence):
    checks = {
        "closed_market_paper_trade": bool(evidence.get("closed_market_paper_trade")),
        "out_of_sample_positive_net_expectancy": bool(evidence.get("out_of_sample_positive_net_expectancy")),
        "protected_demo_bracket_verified": bool(evidence.get("protected_demo_bracket_verified")),
        "live_order_adapter_reviewed": bool(evidence.get("live_order_adapter_reviewed")),
        "kill_switch_and_reconciliation_verified": bool(evidence.get("kill_switch_and_reconciliation_verified")),
    }
    return {"ready_for_live_review": all(checks.values()), "checks": checks,
            "missing": [name for name, passed in checks.items() if not passed],
            "live_armed": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_json", type=Path)
    args = parser.parse_args()
    result = gate(json.loads(args.evidence_json.read_text()))
    print(json.dumps(result, indent=2))
    return 0 if result["ready_for_live_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
