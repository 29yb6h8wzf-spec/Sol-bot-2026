"""Offline release-gate tests: never authorize execution or touch live."""
import importlib.util
import json
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "tools" / "offline_release_gate.py"
SPEC = importlib.util.spec_from_file_location("signalpilot_read_only_release_gate", SOURCE)
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
STAGING_SHA = "a" * 40
ACTIVE_SHA = "b" * 40


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    stage = tmp_path / "research_stage"
    active = tmp_path / "active"
    stage.mkdir()
    active.mkdir()
    evidence = {
        "mode": "RESEARCH_STAGING_ONLY_NO_EXECUTION",
        "staging_systemd_services_installed": False,
        "exchange_orders_sent": False,
        "source_branches_unmerged": True,
        "base_production_sha": ACTIVE_SHA,
        "verified_history_gate": "NOT_ENOUGH_VERIFIED_HISTORY",
    }
    (stage / "staging-results.json").write_text(json.dumps(evidence))
    (active / "binance-paper-status.json").write_text(
        json.dumps({"live_orders_enabled": False}))
    monkeypatch.setattr(
        GATE, "_sha", lambda path: STAGING_SHA if Path(path) == stage else ACTIVE_SHA)
    monkeypatch.setattr(GATE, "_tracked_dirty", lambda path: False)
    return stage, active, evidence


def check(fixture, **kwargs):
    stage, active, _ = fixture
    return GATE.check_release_gate(
        staging_dir=stage, active_dir=active,
        expected_staging_sha=kwargs.pop("expected_staging_sha", STAGING_SHA),
        **kwargs)


def test_clean_offline_stage_is_eligible_for_review_but_not_live(fixture):
    r = check(fixture)
    assert r["status"] == "BLOCKED_RESEARCH_GATE"
    assert r["offline_staging_checks_passed"] is True
    assert r["staging_sha_match"] is True
    assert r["active_production_sha_unchanged"] is True
    assert "90_day_history_not_complete" in r["reasons"]
    assert "historical_source_authentication_not_proven" in r["reasons"]
    assert r["production_ready"] is False
    assert r["orders_sent"] is False
    assert r["execution_authorized"] is False


def test_a_fabricated_complete_90day_gate_still_cannot_authorize_trading(fixture):
    stage, _, evidence = fixture
    evidence["verified_history_gate"] = (
        "OHLCV_CONTINUITY_COMPLETE_PROVENANCE_UNAUTHENTICATED")
    (stage / "staging-results.json").write_text(json.dumps(evidence))
    r = check(fixture)
    assert "90_day_history_not_complete" not in r["reasons"]
    assert "historical_source_authentication_not_proven" in r["reasons"]
    assert r["production_ready"] is False


def test_observed_revision_mismatch_blocks_staging(fixture):
    r = check(fixture, expected_staging_sha="c"*40)
    assert "staging_commit_mismatch" in r["reasons"]
    assert r["offline_staging_checks_passed"] is False


def test_tracked_dirty_files_block_staging(fixture, monkeypatch):
    monkeypatch.setattr(GATE, "_tracked_dirty", lambda path: True)
    r = check(fixture)
    assert "staging_tracked_changes" in r["reasons"]
    assert r["offline_staging_checks_passed"] is False


def test_live_mode_becoming_enabled_blocks_staging(fixture):
    stage, active, _ = fixture
    (active / "binance-paper-status.json").write_text(
        json.dumps({"live_orders_enabled": True}))
    r = check(fixture)
    assert "live_trading_not_verified_disabled" in r["reasons"]
    assert r["offline_staging_checks_passed"] is False


def test_missing_live_flag_fails_closed(fixture):
    _, active, _ = fixture
    (active / "binance-paper-status.json").write_text("{}")
    r = check(fixture)
    assert "live_trading_not_verified_disabled" in r["reasons"]


@pytest.mark.parametrize("field,value,reason", [
    ("mode", "PRODUCTION", "incorrect_staging_mode"),
    ("staging_systemd_services_installed", True, "staging_services_not_isolated"),
    ("exchange_orders_sent", True, "staging_orders_not_verified_disabled"),
    ("source_branches_unmerged", False, "branch_review_scope_not_verified"),
    ("base_production_sha", "c"*40, "active_production_revision_changed"),
])
def test_untrusted_staging_claims_do_not_override_gates(fixture, field, value, reason):
    stage, _, evidence = fixture
    evidence[field] = value
    (stage / "staging-results.json").write_text(json.dumps(evidence))
    r = check(fixture)
    assert reason in r["reasons"]
    assert r["offline_staging_checks_passed"] is False


def test_broken_or_missing_evidence_blocks_even_offline_review(fixture):
    stage, _, _ = fixture
    (stage / "staging-results.json").write_text("not JSON")
    r = check(fixture)
    assert r["status"] == "BLOCKED_RESEARCH_GATE"
    assert "missing_or_invalid_evidence" in r["reasons"]
    assert r["production_ready"] is False
    assert r["execution_authorized"] is False


def test_bad_expected_sha_never_succeeds(fixture):
    with pytest.raises(ValueError, match="invalid_expected_sha"):
        check(fixture, expected_staging_sha="main")


def test_no_sensitive_paths_reported_when_input_file_missing(fixture):
    stage, active, _ = fixture
    (active / "binance-paper-status.json").unlink()
    r = check(fixture)
    assert r["reasons"] == ["missing_or_invalid_evidence"]
    assert str(active) not in json.dumps(r)
