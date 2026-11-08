"""Fail-closed recovery orchestration for a possibly filled live entry.

This is an integration building block, not a live trading entrypoint.
No credentials, arming, strategy signals or exchange client are constructed here.
"""
from live_emergency_recovery import RecoveryIncomplete, flatten_then_cleanup


class CriticalRecoveryError(RuntimeError):
    pass


def recover_possible_entry(exchange, symbol, signal_id, journal):
    """Assume an entry MAY have filled even if its acknowledgement was lost.

    Always reconcile actual exchange exposure, including after network timeout.
    On any failed verification preserve existing protections and escalate.
    """
    journal.mark(signal_id, "RECOVERY_STARTED_ENTRY_MAY_HAVE_FILLED")
    try:
        result = flatten_then_cleanup(exchange, symbol)
    except Exception as exc:
        journal.mark(signal_id, "CRITICAL_RECOVERY_INCOMPLETE_PROTECTIONS_PRESERVED_IF_POSSIBLE")
        raise CriticalRecoveryError(
            "Live position state unresolved; halt all entries and inspect exchange"
        ) from exc
    journal.mark(signal_id, "RECOVERY_VERIFIED_FLAT")
    return result
