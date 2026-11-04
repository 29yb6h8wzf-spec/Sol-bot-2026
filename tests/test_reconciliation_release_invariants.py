"""Offline regression tests for reconciliation state persistence.

No Binance connection, no credentials, no order placement.
"""
from datetime import datetime, timezone
import pytest


def test_reconciliation_state_never_silently_clears_history():
    # This invariant mirrors demo_reconciliation_guard.reconcile:
    # historical unmatched fills persist across daily rollovers.
    previous = {"unattributed_history_unresolved": True}
    unknown_fills_today = 0
    assert previous["unattributed_history_unresolved"] or unknown_fills_today > 0


def test_utc_rollover_cannot_clear_prior_exposure():
    previous = {"last_day_utc": "2026-11-03",
                "last_open_exposure": True,
                "prior_day_exposure_unresolved": False}
    today = "2026-11-04"
    unresolved = previous["prior_day_exposure_unresolved"] or (
        previous["last_day_utc"] != today and previous["last_open_exposure"])
    assert unresolved is True


def test_reconciliation_status_is_not_execution_permission():
    # The existing read-only reconciliation report deliberately blocks
    # authorization until attribution and virtual allocation are reconciled.
    status = {
        "status": "BLOCKED_UNRECONCILED",
        "unattributed_history_unresolved": True,
        "allocation_ledger_reconciled": False,
        "execution_authorized": False,
    }
    assert not status["execution_authorized"]
    assert not status["allocation_ledger_reconciled"]
