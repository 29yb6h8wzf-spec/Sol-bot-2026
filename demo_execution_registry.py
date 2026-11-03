"""Trusted receipt registry for Binance Futures DEMO only.

No order creation. An entry is written only AFTER Binance independently
confirms its order ID, symbol and deterministic SignalPilot client order ID.
This module does not enable execution, reconcile allocation, or approve risk.
"""
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path

from demo_account_observer import assert_demo, save_observation
from demo_trade_attribution import SYMBOLS, REGISTRY, registry_orders

LEGS = frozenset(("entry", "stop", "target"))
SIGNAL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
ORDER_RE = re.compile(r"^[0-9]{1,30}$")


def client_order_id(signal_id, leg="entry"):
    if not isinstance(signal_id, str) or not SIGNAL_RE.fullmatch(signal_id):
        raise ValueError("invalid_signal_id")
    if leg not in LEGS:
        raise ValueError("invalid_order_leg")
    digest = hashlib.sha256((signal_id + ":" + leg).encode("utf-8")).hexdigest()[:24]
    return "SPDEMO-" + digest


def verify_exchange_order(exchange, *, signal_id, leg, symbol, order_id):
    assert_demo(exchange)
    if symbol not in SYMBOLS or not isinstance(order_id, str) or not ORDER_RE.fullmatch(order_id):
        raise ValueError("invalid_order_identity")
    client = client_order_id(signal_id, leg)
    order = exchange.fetch_order(order_id, symbol)
    if (not isinstance(order, dict) or str(order.get("id")) != order_id or
            order.get("symbol") != symbol or order.get("clientOrderId") != client):
        raise ValueError("exchange_order_provenance_mismatch")
    return {"symbol": symbol, "order_id": order_id, "client_order_id": client,
            "signal_id": signal_id, "leg": leg}


def record_confirmed_order(exchange, *, signal_id, leg, symbol, order_id,
                           registry_path=REGISTRY):
    """Append Binance-confirmed order identity, idempotently, with file lock.

    The caller must be the future trusted demo executor. Never use this to
    import historical unrelated orders, and never infer ownership from price.
    """
    assert_demo(exchange)
    row = verify_exchange_order(exchange, signal_id=signal_id, leg=leg,
                                symbol=symbol, order_id=order_id)
    path = Path(registry_path)
    if path.is_symlink():
        raise ValueError("registry_symlink_not_allowed")
    if path.parent.is_symlink() or path.parent.stat().st_uid != 0:
        raise ValueError("untrusted_registry_directory")
    lock_path = path.with_name(path.name + ".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_uid != 0 or os.fstat(fd).st_mode & 0o077:
            raise ValueError("untrusted_registry_lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        existing, present = registry_orders(path)
        for prior in existing.values():
            if prior["client_order_id"] == row["client_order_id"]:
                if prior == row:
                    return "ALREADY_RECORDED"
                raise ValueError("conflicting_client_order_id")
        if (symbol, order_id) in existing:
            raise ValueError("conflicting_exchange_order_id")
        orders = list(existing.values()) + [row]
        save_observation({
            "schema_version": 1,
            "source": "signalpilot_demo_executor_registry",
            "execution_mode": "binance_demo",
            "orders": orders,
        }, path)
        return "RECORDED_VERIFIED_RECEIPT"
    finally:
        os.close(fd)
