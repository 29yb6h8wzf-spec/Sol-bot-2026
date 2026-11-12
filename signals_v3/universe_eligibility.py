"""Point-in-time universe eligibility for offline research only.

A price band is not a profitability or execution authorization.
"""
from decimal import Decimal, InvalidOperation

MIN_PRICE = Decimal("0.99")
MAX_PRICE = Decimal("150")

class UniverseRejected(ValueError):
    pass

def _decimal(value, field):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise UniverseRejected(field + "_invalid")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise UniverseRejected(field + "_invalid") from None
    if not result.is_finite():
        raise UniverseRejected(field + "_nonfinite")
    return result

def eligible_contract(contract, ticker, decision_ms, max_age_ms=300000):
    """Fail closed on stale, missing, non-USDT perpetual or non-trading records.

    Caller must supply an authentic archived point-in-time contract and ticker.
    This pure function does not fetch or assert authenticity of historical data.
    """
    if not isinstance(contract, dict) or not isinstance(ticker, dict):
        raise UniverseRejected("record_invalid")
    if isinstance(decision_ms, bool) or not isinstance(decision_ms, int) or decision_ms <= 0:
        raise UniverseRejected("decision_time_invalid")
    if isinstance(max_age_ms, bool) or not isinstance(max_age_ms, int) or max_age_ms < 0:
        raise UniverseRejected("max_age_invalid")
    symbol = contract.get("symbol")
    if not isinstance(symbol, str) or not symbol.endswith("USDT") or not symbol[:-4]:
        raise UniverseRejected("symbol_invalid")
    if (contract.get("quoteAsset") != "USDT"
            or contract.get("contractType") != "PERPETUAL"
            or contract.get("status") != "TRADING"
            or ticker.get("symbol") != symbol):
        raise UniverseRejected("contract_ineligible")
    timestamp = ticker.get("timestamp_ms")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        raise UniverseRejected("timestamp_invalid")
    if timestamp > decision_ms or decision_ms - timestamp > max_age_ms:
        raise UniverseRejected("timestamp_outside_decision_window")
    price = _decimal(ticker.get("price"), "price")
    if price <= 0:
        raise UniverseRejected("price_nonpositive")
    return MIN_PRICE <= price <= MAX_PRICE
