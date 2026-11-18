"""Offline CLI: summarize SOL/XRP strategy setups from a local JSONL replay.

Usage:
    python -m futures_engine.research_setup_score_report --input replay.jsonl --output report.json

Input lines must be JSON objects with {"symbol": ..., "setups": [...]}.
No network calls, order execution, or changes to the live score gate.
"""
import argparse
import json
from pathlib import Path

from futures_engine.research_setup_score_distribution import summarize_setups


def build_report(source):
    scans = []
    for line_number, line in enumerate(source, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid_json_line_{line_number}") from exc
        scans.append(item)
    if not scans:
        raise ValueError("empty_replay")
    return summarize_setups(scans)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Existing local JSONL replay")
    parser.add_argument("--output", required=True, help="New local JSON report")
    args = parser.parse_args(argv)
    input_path = Path(args.input).resolve(strict=True)
    output_path = Path(args.output).resolve()
    if input_path == output_path:
        parser.error("input_and_output_must_differ")
    with input_path.open("r", encoding="utf-8") as source:
        result = build_report(source)
    with output_path.open("x", encoding="utf-8") as target:
        json.dump(result, target, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps({"scans": result["totals"]["scans"],
                      "setups": result["totals"]["setups"],
                      "output_created": True,
                      "execution_authorized": False}))


if __name__ == "__main__":
    main()
