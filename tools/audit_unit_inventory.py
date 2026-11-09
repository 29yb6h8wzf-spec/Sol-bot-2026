"""Read-only audit: can Git reconstruct installed SignalPilot systemd entrypoints?

Does NOT run the services, inspect environment files, reveal systemd commands,
contact exchanges, or change the machine. Only reports Git-tracking coverage.
Use --strict for CI once all required service units have been versioned.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

PY_MODULE = re.compile(r"(?:^|\s)-m\s+([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)")
PY_SCRIPT = re.compile(r"(?<![\w.])((?:/opt/signalpilot/|\./)?[\w./-]+\.(?:py|sh))\b")


def git_tracked_paths(repo):
    """Return the version-controlled file set without reading file contents."""
    names = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "-z"],
        timeout=20,
    ).decode("utf-8")
    return frozenset(name for name in names.split("\0") if name)


def entrypoint_paths(execstart_line):
    """Best-effort Python and shell entrypoint discovery (no command secrets)."""
    modules = [m.group(1) for m in PY_MODULE.finditer(execstart_line)]
    scripts = []
    for match in PY_SCRIPT.finditer(execstart_line):
        raw = match.group(1)
        if raw.startswith("/opt/signalpilot/"):
            raw = raw[len("/opt/signalpilot/"):]
        elif raw.startswith("/"):
            continue  # system Python, not part of the project
        else:
            raw = raw.removeprefix("./")
        candidate = Path(raw)
        if ".." not in candidate.parts and raw:
            scripts.append(raw)
    return modules, scripts


def audit_service_units(installed_dir, tracked, unit_names=None):
    """Compare named installed units against tracked unit and entrypoint paths.

    Passing unit_names is intentional: only audit confirmed live service units,
    rather than assuming every historical file in the installed directory is
    active. A missing named unit is recorded as a problem, not ignored.
    """
    installed_dir = Path(installed_dir)
    if unit_names is None:
        names = sorted(p.name for p in installed_dir.glob("signalpilot-*.service"))
    else:
        names = sorted(set(unit_names))
    report = []
    for name in names:
        if (not name.startswith("signalpilot-") or
                not name.endswith(".service") or Path(name).name != name):
            raise ValueError("invalid_unit_name")
        unit_file = installed_dir / name
        tracked_unit = "deploy/systemd/" + name in tracked
        if not unit_file.is_file():
            report.append({"unit": name, "installed": False,
                           "unit_tracked": tracked_unit,
                           "entrypoints": []})
            continue
        commands = [line.split("=", 1)[1] for line in
                    unit_file.read_text().splitlines()
                    if line.startswith("ExecStart=")]
        entrypoints = []
        for cmd in commands:
            mods, scripts = entrypoint_paths(cmd)
            for mod in mods:
                path = mod.replace(".", "/")
                # python -m package needs package/__main__.py, not __init__.py
                candidates = (path + ".py", path + "/__main__.py")
                covered = any(candidate in tracked for candidate in candidates)
                entrypoints.append({"module": mod, "tracked": covered})
            for path in scripts:
                if path not in {mod.replace(".", "/") + ".py" for mod in mods}:
                    entrypoints.append({"script": path, "tracked": path in tracked})
        report.append({"unit": name, "installed": True,
                       "unit_tracked": tracked_unit,
                       "entrypoints": entrypoints})
    missing = sum((not item["installed"] or not item["unit_tracked"] or
                   any(not entry["tracked"] for entry in item["entrypoints"]))
                  for item in report)
    return {"units_checked": len(report), "units_with_gaps": missing,
            "services": report, "read_only": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/opt/signalpilot"))
    parser.add_argument("--installed-units", type=Path,
                        default=Path("/etc/systemd/system"))
    parser.add_argument("--unit", action="append", default=None,
                        help="A confirmed installed SignalPilot service to audit")
    parser.add_argument("--strict", action="store_true",
                        help="Return nonzero if any installed/track gap is found")
    args = parser.parse_args(argv)
    result = audit_service_units(
        args.installed_units, git_tracked_paths(args.repo), args.unit)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if args.strict and result["units_with_gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
