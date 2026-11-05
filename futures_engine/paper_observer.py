"""Read-only Paper ledger event counters for the existing status snapshot.

Never talks to an exchange or changes a Paper ledger. All data is observational.
"""


def summarize_ledger(state):
    """Return a narrow, JSON-safe lifecycle summary from a PaperLedger state."""
    if not isinstance(state, dict):
        raise ValueError("invalid_paper_state")
    events = state.get("history")
    if not isinstance(events, list):
        raise ValueError("invalid_paper_history")
    entries = 0
    exits = 0
    latest = None
    for item in events:
        if not isinstance(item, dict):
            raise ValueError("invalid_paper_event")
        kind = item.get("event")
        if kind == "paper_entry":
            entries += 1
            timestamp = item.get("signal_candle")
        elif kind == "paper_exit":
            exits += 1
            timestamp = item.get("timestamp")
        else:
            raise ValueError("unknown_paper_event")
        if type(timestamp) is not int or timestamp < 0:
            raise ValueError("invalid_paper_timestamp")
        latest = {"event": kind, "candle_ms": timestamp}
        if kind == "paper_exit":
            if item.get("reason") not in ("stop", "target"):
                raise ValueError("invalid_paper_exit_reason")
            latest["reason"] = item["reason"]
            # PnL is reported as a string, never interpreted as a success rate.
            latest["pnl"] = str(item.get("pnl"))
    position = state.get("position")
    if position is not None and not isinstance(position, dict):
        raise ValueError("invalid_paper_position")
    if exits > entries or entries - exits != (1 if position else 0):
        raise ValueError("inconsistent_paper_history")
    last_signal = state.get("last_signal_candle")
    if last_signal is not None and (type(last_signal) is not int or last_signal < 0):
        raise ValueError("invalid_last_signal_candle")
    return {
        "paper_entries": entries,
        "paper_exits": exits,
        "history_count": len(events),
        "last_paper_event": latest,
        "last_signal_candle": last_signal,
    }
