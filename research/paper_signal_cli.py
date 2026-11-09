"""Offline CLI for replaying a saved SignalPilot scanner result.

Inputs are local files; this command never fetches market data or places orders.
Usage:
python -m research.paper_signal_cli --scan scan.json --bars bars.json \\
  --quantity 0.8 --entry-mid 86 --stop 85 --target 88 --db paper.sqlite3
"""
import argparse
import json
from pathlib import Path

from research.paper_signal_adapter import replay_scanner_candidate


def main():
    parser = argparse.ArgumentParser(description="Offline SignalPilot scanner-to-paper replay")
    parser.add_argument("--scan", required=True, type=Path)
    parser.add_argument("--bars", required=True, type=Path)
    parser.add_argument("--quantity", required=True)
    parser.add_argument("--entry-mid", required=True)
    parser.add_argument("--stop", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--candidate-index", type=int, default=0)
    args = parser.parse_args()
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    bars = json.loads(args.bars.read_text(encoding="utf-8"))
    result = replay_scanner_candidate(
        scan, quantity=args.quantity, entry_mid=args.entry_mid,
        stop=args.stop, target=args.target, bars=bars,
        database_path=args.db, candidate_index=args.candidate_index,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
