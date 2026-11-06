"""Regression tests for the offline service inventory; no systemd calls."""
import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "audit_unit_inventory.py"
SPEC = importlib.util.spec_from_file_location("audit_unit_inventory", SOURCE)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def unit(directory, name, command):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text("[Unit]\nDescription=Fixture\n"
                                  "[Service]\nExecStart=" + command + "\n")


def test_python_m_package_entrypoint_is_main_not_init(tmp_path):
    name = "signalpilot-paper-btc.service"
    unit(tmp_path, name, "/opt/signalpilot/.venv/bin/python -m futures_engine")
    good = AUDIT.audit_service_units(
        tmp_path, {"deploy/systemd/" + name, "futures_engine/__main__.py"},
        [name])
    assert good["units_with_gaps"] == 0
    broken = AUDIT.audit_service_units(
        tmp_path, {"deploy/systemd/" + name, "futures_engine/__init__.py"},
        [name])
    assert broken["units_with_gaps"] == 1
    assert broken["services"][0]["entrypoints"] == [
        {"module": "futures_engine", "tracked": False}]


def test_untracked_python_module_is_a_reproducibility_gap(tmp_path):
    name = "signalpilot-sandbox-publisher.service"
    unit(tmp_path, name, "/opt/signalpilot/.venv/bin/python "
                         "-m futures_engine.sandbox_research_publisher")
    result = AUDIT.audit_service_units(
        tmp_path, {"deploy/systemd/" + name}, [name])
    assert result["units_with_gaps"] == 1
    assert result["services"][0]["unit_tracked"] is True
    assert result["services"][0]["entrypoints"] == [
        {"module": "futures_engine.sandbox_research_publisher",
         "tracked": False}]


def test_missing_installed_unit_is_not_silently_ignored(tmp_path):
    name = "signalpilot-strategy-research.service"
    result = AUDIT.audit_service_units(
        tmp_path, {"deploy/systemd/" + name}, [name])
    assert result["units_checked"] == 1
    assert result["units_with_gaps"] == 1
    assert result["services"][0]["installed"] is False


def test_untracked_service_unit_is_reported_even_with_tracked_module(tmp_path):
    name = "signalpilot-strategy-research.service"
    unit(tmp_path, name, "/opt/signalpilot/.venv/bin/python "
                         "-m futures_engine.verified_strategy_scan")
    result = AUDIT.audit_service_units(
        tmp_path, {"futures_engine/verified_strategy_scan.py"}, [name])
    assert result["units_with_gaps"] == 1
    assert result["services"][0]["unit_tracked"] is False
    assert result["services"][0]["entrypoints"][0]["tracked"] is True


def test_direct_script_path_is_detected_without_exposing_arguments(tmp_path):
    name = "signalpilot-binance-telegram-bridge.service"
    unit(tmp_path, name, "/opt/signalpilot/.venv/bin/python "
                         "/opt/signalpilot/binance_telegram_bridge.py "
                         "--token secret-fixture")
    result = AUDIT.audit_service_units(
        tmp_path, {"deploy/systemd/" + name, "binance_telegram_bridge.py"},
        [name])
    assert result["units_with_gaps"] == 0
    assert result["services"][0]["entrypoints"] == [
        {"script": "binance_telegram_bridge.py", "tracked": True}]
    assert "secret-fixture" not in str(result)


def test_relative_direct_script_path_is_checked(tmp_path):
    name = "signalpilot-research-paper-bridge.service"
    unit(tmp_path, name, "/usr/bin/python3 ./research_paper_bridge.py")
    result = AUDIT.audit_service_units(tmp_path, {
        "deploy/systemd/" + name, "research_paper_bridge.py"}, [name])
    assert result["units_with_gaps"] == 0


def test_multiple_modules_are_all_checked(tmp_path):
    name = "signalpilot-checker.service"
    unit(tmp_path, name, "/bin/bash -lc 'python -m alpha.worker "
                         "&& python -m beta.worker'")
    result = AUDIT.audit_service_units(tmp_path, {
        "deploy/systemd/" + name, "alpha/worker.py"}, [name])
    assert result["units_with_gaps"] == 1
    assert len(result["services"][0]["entrypoints"]) == 2


def test_service_name_path_traversal_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid_unit_name"):
        AUDIT.audit_service_units(tmp_path, set(),
                                  ["../signalpilot-other.service"])


def test_empty_inventory_no_false_positive(tmp_path):
    result = AUDIT.audit_service_units(tmp_path, set(), [])
    assert result["units_checked"] == 0
    assert result["units_with_gaps"] == 0


def test_entrypoint_scanner_excludes_system_python_path():
    mods, scripts = AUDIT.entrypoint_paths(
        "/usr/bin/python3 /usr/lib/python3.11/sitecustomize.py "
        "&& python -m futures_engine.verified_strategy_scan")
    assert mods == ["futures_engine.verified_strategy_scan"]
    assert scripts == []
