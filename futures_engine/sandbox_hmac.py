"""Sandbox envelope HMAC-SHA256 authentication primitives.

This module does not access AWS, queues, trading, or persistent storage.
Signing authenticates possession of a shared secret, not independent
verification of a trading strategy or the market data behind it.
"""
import hashlib
import hmac
import json
import time

VERSION = "hmac-sha256-v1"
MAX_AGE_SECONDS = 120
MAX_FUTURE_SKEW_SECONDS = 30


def canonical_bytes(envelope):
    if not isinstance(envelope, dict):
        raise ValueError("invalid envelope")
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _key(secret):
    if not isinstance(secret, (bytes, bytearray)) or len(secret) < 32:
        raise ValueError("HMAC secret must be at least 32 bytes")
    return bytes(secret)


def sign(envelope, *, secret, now=None):
    if not isinstance(envelope, dict) or "authentication" in envelope:
        raise ValueError("invalid unsigned envelope")
    now = int(time.time()) if now is None else int(now)
    signed = dict(envelope)
    signed["authentication"] = {"version": VERSION, "issued_at": now}
    mac = hmac.new(_key(secret), canonical_bytes(signed), hashlib.sha256)
    signed["authentication"]["signature"] = mac.hexdigest()
    return signed


def verify(signed, *, secret, now=None):
    now = int(time.time()) if now is None else int(now)
    if not isinstance(signed, dict):
        raise ValueError("invalid signed envelope")
    auth = signed.get("authentication")
    if not isinstance(auth, dict) or set(auth) != {
        "version", "issued_at", "signature"
    }:
        raise ValueError("missing or malformed authentication")
    if auth["version"] != VERSION:
        raise ValueError("unsupported authentication version")
    issued = auth["issued_at"]
    if type(issued) is not int or issued > now + MAX_FUTURE_SKEW_SECONDS or (
        now - issued > MAX_AGE_SECONDS
    ):
        raise ValueError("expired or future signature")
    signature = auth["signature"]
    if not isinstance(signature, str) or len(signature) != 64:
        raise ValueError("invalid signature")
    try:
        bytes.fromhex(signature)
    except ValueError as exc:
        raise ValueError("invalid signature encoding") from exc
    unsigned_auth = {k: v for k, v in auth.items() if k != "signature"}
    payload = dict(signed)
    payload["authentication"] = unsigned_auth
    expected = hmac.new(_key(secret), canonical_bytes(payload), hashlib.sha256)
    if not hmac.compare_digest(signature, expected.hexdigest()):
        raise ValueError("signature mismatch")
    return {k: v for k, v in signed.items() if k != "authentication"}
