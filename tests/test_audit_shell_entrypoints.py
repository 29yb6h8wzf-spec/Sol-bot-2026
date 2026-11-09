"""Ensure shell entrypoints cannot silently pass reproducibility audits."""
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "audit_unit_inventory.py"
SPEC = importlib.util.spec_from_file_location("audit_unit_inventory_shell", SOURCE)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_untracked_shell_entrypoint_is_a_gap(tmp_path):
    name = "signalpilot-sandbox-worker.service"
    (tmp_path / name).write_text(
        "[Service]\nExecStart=/bin/bash /opt/signalpilot/scripts/start_sandbox.sh --token secret-fixture\n"
    )
    result = AUDIT.audit_service_units(
        tmp_path, {"deploy/systemd/" + name}, [name]
    )
    assert result["units_with_gaps"] == 1
    assert result["services"][0]["entrypoints"] == [
        {"script": "scripts/start_sandbox.sh", "tracked": False}
    ]
    assert "secret-fixture" not in str(result)


def test_tracked_shell_entrypoint_passes(tmp_path):
    name = "signalpilot-sandbox-worker.service"
    (tmp_path / name).write_text(
        "[Service]\nExecStart=/bin/bash /opt/signalpilot/scripts/start_sandbox.sh\n"
    )
    result = AUDIT.audit_service_units(
        tmp_path, {"deploy/systemd/" + name, "scripts/start_sandbox.sh"}, [name]
    )
    assert result["units_with_gaps"] == 0
