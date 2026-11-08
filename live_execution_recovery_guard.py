"""Fail-closed boundary for an entry that may have reached Binance.

No exchange client, credentials, arming or live entry are created here.
This module must be reviewed before wiring into the real executor.
"""
from live_recovery_orchestrator import recover_possible_entry, CriticalRecoveryError


class EntryRecoveryRequired(RuntimeError):
    pass


def submit_with_recovery(exchange, symbol, signal_id, journal, submit_entry):
    """On *any* entry exception assume fill is possible and reconcile/flatten.

    Callers must halt trading on EntryRecoveryRequired or CriticalRecoveryError.
    Never retry the entry automatically.
    """
    journal.mark(signal_id, "ENTRY_SUBMITTING")
    try:
        result = submit_entry()
    except BaseException as exc:
        # KeyboardInterrupt/SystemExit may interrupt after the exchange accepted an order.
        try:
            recover_possible_entry(exchange, symbol, signal_id, journal)
        except CriticalRecoveryError:
            raise
        raise EntryRecoveryRequired("entry outcome uncertain; verified flat; do not retry") from exc
    journal.mark(signal_id, "ENTRY_ACKNOWLEDGED")
    return result
