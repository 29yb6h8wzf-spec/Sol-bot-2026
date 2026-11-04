"""Offline integration contract for the EC2 signal inbox.

This module is intentionally safe: temporary SQLite only, no AWS, Binance,
Cloudflare, Telegram, production queue, or order submission.
"""
import importlib.util
import time
from pathlib import Path

import pytest


def load_inbox():
    path = Path(__file__).resolve().parents[1] / "signal_inbox.py"
    if not path.is_file():
        pytest.skip("EC2-only signal_inbox.py not yet reconciled into repository")
    spec = importlib.util.spec_from_file_location("signal_inbox_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(**changes):
    value = {
        "signal_id": "offline-contract-001",
        "symbol": "XRPUSDT",
        "direction": "long",
        "score": 85,
        "timestamp": int(time.time()),
        "source": "verified_85_score_engine",
    }
    value.update(changes)
    return value


def test_accept_then_deduplicate(tmp_path):
    inbox = load_inbox()
    db = str(tmp_path / "inbox.sqlite3")
    signal = payload()
    assert inbox.accept(signal, db=db) is True
    assert inbox.accept(signal, db=db) is False


@pytest.mark.parametrize("changes", [
    {"score": 84},
    {"score": 101},
    {"score": True},
    {"source": "telegram"},
    {"symbol": "DOGEUSDT"},
    {"direction": "buy"},
    {"timestamp": 0},
    {"signal_id": "bad id"},
    {"entry": "123.45"},
])
def test_fail_closed_for_invalid_payload(tmp_path, changes):
    inbox = load_inbox()
    with pytest.raises(ValueError):
        inbox.accept(payload(**changes), db=str(tmp_path / "inbox.sqlite3"))


def test_separate_inbox_databases_do_not_share_signals(tmp_path):
    inbox = load_inbox()
    signal = payload()
    assert inbox.accept(signal, db=str(tmp_path / "a.sqlite3"))
    assert inbox.accept(signal, db=str(tmp_path / "b.sqlite3"))
