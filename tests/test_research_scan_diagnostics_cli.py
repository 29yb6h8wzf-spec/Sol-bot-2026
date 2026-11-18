"""Read-only SQLite diagnostic report integration tests."""
import json
import sqlite3

import pytest

from futures_engine.research_scan_diagnostics_cli import report_from_sqlite


def test_report_reads_existing_database_without_modification(tmp_path):
    path = tmp_path / "research.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE research_scans (id INTEGER PRIMARY KEY, payload TEXT)")
        db.execute("INSERT INTO research_scans(payload) VALUES (?)", (json.dumps({
            "symbol": "SOL", "status": "RESEARCH_ONLY",
            "scan_diagnostics": {
                "setups_seen": 2, "below_threshold": 1,
                "invalid_score": 0, "verification_rejected": 0,
                "eligible": 1, "no_setup": False,
            },
        }),))
        db.execute("INSERT INTO research_scans(payload) VALUES (?)", (json.dumps({
            "symbol": "XRP", "status": "RESEARCH_ONLY",
        }),))
        db.commit()
    before = path.read_bytes()
    report = report_from_sqlite(str(path))
    assert report["totals"]["scans"] == 2
    assert report["totals"]["below_threshold"] == 1
    assert report["totals"]["legacy_scans_without_diagnostics"] == 1
    assert report["execution_authorized"] is False
    assert path.read_bytes() == before


def test_report_missing_database_does_not_create_file(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        report_from_sqlite(str(path))
    assert not path.exists()


def test_report_rejects_corrupt_json(tmp_path):
    path = tmp_path / "bad.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE research_scans (id INTEGER PRIMARY KEY, payload TEXT)")
        db.execute("INSERT INTO research_scans(payload) VALUES ('not-json')")
        db.commit()
    with pytest.raises(json.JSONDecodeError):
        report_from_sqlite(str(path))


def test_cli_outputs_json_without_touching_database(tmp_path, capsys):
    from futures_engine.research_scan_diagnostics_cli import main
    path = tmp_path / "research.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE research_scans (id INTEGER PRIMARY KEY, payload TEXT)")
        db.execute("INSERT INTO research_scans(payload) VALUES (?)", (json.dumps({
            "symbol": "SOL/USDT:USDT", "status": "RESEARCH_ONLY",
            "scan_diagnostics": {
                "setups_seen": 0, "below_threshold": 0, "invalid_score": 0,
                "verification_rejected": 0, "eligible": 0, "no_setup": True,
            },
        }),))
        db.commit()
    before = path.read_bytes()
    main(["--db", str(path)])
    report = json.loads(capsys.readouterr().out)
    assert report["totals"]["no_setup_scans"] == 1
    assert report["totals"]["scans"] == 1
    assert report["execution_authorized"] is False
    assert path.read_bytes() == before
