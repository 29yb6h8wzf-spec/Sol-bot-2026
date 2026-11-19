"""Read-only SQLite adapter for offline SignalPilot scan diagnostic reports."""
import argparse
import json
import sqlite3

from futures_engine.research_scan_diagnostics_report import summarize_scan_diagnostics


def report_from_sqlite(db_path):
    # mode=ro prevents creating or modifying the research database.
    from pathlib import Path
    path = Path(db_path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("not_a_database_file")
    uri = path.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        def rows():
            for (payload,) in connection.execute(
                "SELECT payload FROM research_scans ORDER BY id"
            ):
                yield json.loads(payload)
        return summarize_scan_diagnostics(rows())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Existing research-history SQLite file")
    args = parser.parse_args(argv)
    print(json.dumps(report_from_sqlite(args.db), sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
