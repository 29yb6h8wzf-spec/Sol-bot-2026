"""Read-only historical audit coverage. Missing days are never clean."""
from datetime import date, timedelta


def coverage(start, end, reports):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    count = (last - first).days + 1
    if not 1 <= count <= 31:
        raise ValueError("invalid_window")
    result = []
    for offset in range(count):
        day = (first + timedelta(days=offset)).isoformat()
        item = reports.get(day)
        if item is None:
            result.append({"day": day, "status": "MISSING"})
        elif (item.get("status") != "AUDIT_ONLY_NOT_EXECUTABLE"
              or item.get("execution_authorized") is not False):
            raise ValueError("untrusted_report")
        else:
            result.append({"day": day, "status": "PARTIAL_AUDIT"})
    return {"days": result, "reconciled": False,
            "execution_authorized": False, "orders_sent": False}
