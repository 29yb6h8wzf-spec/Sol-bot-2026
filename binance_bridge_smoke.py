"""Send exactly one clearly labeled owner-only Telegram bridge smoke test.

No market signal, no prices, no exchange access, no orders. Requires EC2 IAM
permission to read the dedicated research HMAC parameter. No secrets logged.
"""
import json
import secrets
import time
import urllib.error
import urllib.request

from binance_telegram_bridge import check_endpoint, load_ssm_secret, sign_payload

URL = "https://sol-bot-2026.29yb6h8wzf.workers.dev/internal/binance-research"


def smoke():
    stamp = int(time.time())
    payload = {
        "type": "SIGNALPILOT_BINANCE_BRIDGE_TEST_V1",
        "nonce": "test-" + secrets.token_hex(12),
        "timestamp": stamp,
        "execution_authorized": False,
        "orders_sent": False,
    }
    raw, signature = sign_payload(payload, load_ssm_secret(), stamp)
    request = urllib.request.Request(
        check_endpoint(URL), data=raw, method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "SignalPilot-Research-Bridge/1.0",
            "X-Signalpilot-Timestamp": str(stamp),
            "X-Signalpilot-Signature": signature,
        })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            data = json.loads(response.read(512))
    except urllib.error.HTTPError as error:
        print(json.dumps({"status": "FAILED", "http_status": error.code,
                          "orders_sent": False}))
        return False
    success = (status == 200 and data.get("status") == "delivered_owner_only"
               and data.get("test_only") is True and data.get("research_only") is True)
    print(json.dumps({"status": "OWNER_TEST_DELIVERED" if success else "FAILED",
                      "http_status": status, "orders_sent": False}))
    return success


if __name__ == "__main__":
    raise SystemExit(0 if smoke() else 1)
