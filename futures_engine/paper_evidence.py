"""Produce auditable offline paper integration evidence for CI.

Synthetic prices only. Does not contact Binance or submit orders.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

from futures_engine.paper import PaperLedger
from futures_engine.report import summarize_paper_ledger


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m futures_engine.paper_evidence OUTPUT_DIR")
    directory = Path(sys.argv[1])
    directory.mkdir(parents=True, exist_ok=True)
    ledger_path = directory / "paper-ledger.json"
    if ledger_path.exists():
        raise SystemExit("refusing to overwrite existing paper evidence")
    paper = PaperLedger(ledger_path, Decimal("150"))
    paper.bind("BTCUSDT", "5m", 300000)
    paper.open_position({
        "side": "long", "entry": "100", "stop": "99",
        "target": "102", "quantity": "1",
        "fee_rate": "0.001", "slippage_rate": "0",
    }, 900000)
    event = paper.evaluate_exit(
        [[1200000, 100, 103, 100, 101, 1]],
        Decimal("0.001"), Decimal("0"),
    )
    if not event or event["reason"] != "target":
        raise RuntimeError("expected synthetic paper exit")
    report = summarize_paper_ledger(json.loads(ledger_path.read_text()))
    if not report["equity_reconciled"] or report["closed_trades"] != 1:
        raise RuntimeError("paper evidence reconciliation failed")
    (directory / "paper-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (directory / "provenance.json").write_text(json.dumps({
        "source": "synthetic_fixture",
        "market_data": False,
        "real_trading": False,
        "purpose": "offline_ci_integration_evidence"
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
