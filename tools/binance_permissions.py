#!/usr/bin/env python3
"""Check a Binance USD-M mainnet HMAC key using signed, read-only requests.

Run with BINANCE_API_KEY and BINANCE_API_SECRET injected into the environment.
On AWS, use asm-exec with a dynamic reference in BINANCE_CREDENTIALS_JSON
to inject an entire key-pair object without putting credentials in argv.
Exit codes: 0 flags enabled, 1 at least one disabled, 2 inconclusive.
"""

import hashlib
import hmac
import http.client
import json
import os
import ssl
import time


CHECKS = (
    ("api.binance.com", "/sapi/v1/account/apiRestrictions", "enableFutures"),
    ("fapi.binance.com", "/fapi/v1/accountConfig", "canTrade"),
)


def credentials():
    raw = os.environ.get("BINANCE_CREDENTIALS_JSON")
    if raw is None:
        return os.environ.get("BINANCE_API_KEY"), os.environ.get("BINANCE_API_SECRET")

    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("invalid credential format")
    fields = {str(k).lower().replace("_", ""): v for k, v in obj.items()}
    key = next((fields[n] for n in ("binanceapikey", "apikey", "key") if n in fields), None)
    secret = next((fields[n] for n in ("binanceapisecret", "binancesecretkey", "apisecret",
                                      "apisecretkey", "secretkey", "secret") if n in fields), None)
    return key, secret


def read_flag(check, key, secret):
    host, path, flag = check
    query = f"timestamp={time.time_ns() // 1_000_000}&recvWindow=5000"
    signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    conn = http.client.HTTPSConnection(host, timeout=8, context=ssl.create_default_context())
    try:
        conn.request("GET", f"{path}?{query}&signature={signature}", headers={"X-MBX-APIKEY": key})
        response = conn.getresponse()
        payload = response.read(65537)
        if response.status != 200:
            error = {"http_status": response.status}
            try:
                body = json.loads(payload)
                if isinstance(body, dict) and type(body.get("code")) is int:
                    error["binance_code"] = body["code"]
            except (ValueError, UnicodeError):
                pass
            return error
        if len(payload) > 65536:
            return {"error": "response_too_large"}
        obj = json.loads(payload)
        value = obj.get(flag) if isinstance(obj, dict) else None
        if type(value) is bool:
            return {"value": value}
        return {"error": "missing_or_invalid_flag"}
    except (OSError, http.client.HTTPException):
        return {"error": "connection_failed"}
    except (ValueError, UnicodeError):
        return {"error": "invalid_data"}
    finally:
        conn.close()


def run():
    try:
        key, secret = credentials()
        if not all(isinstance(v, str) and v.strip() for v in (key, secret)):
            raise ValueError("missing credentials")
    except ValueError:
        return {"status": "unknown", "error": "missing_or_invalid_credentials"}, 2
    flags = {check[2]: read_flag(check, key, secret) for check in CHECKS}
    values = [flag.get("value") for flag in flags.values()]
    if False in values:
        status, exit_code = "disabled", 1
    elif all(value is True for value in values):
        status, exit_code = "enabled", 0
    else:
        status, exit_code = "unknown", 2
    return {"status": status, "checks": flags}, exit_code


if __name__ == "__main__":
    result, code = run()
    print(json.dumps(result))
    raise SystemExit(code)
