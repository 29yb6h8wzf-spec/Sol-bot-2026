"""Load the sandbox HMAC key from AWS Secrets Manager (read-only)."""
import base64
import binascii
import boto3

SECRET_ID = "signalpilot/sandbox/hmac-v1"
REGION = "il-central-1"


def load_key(*, client=None):
    client = client or boto3.client("secretsmanager", region_name=REGION)
    value = client.get_secret_value(SecretId=SECRET_ID)["SecretString"]
    if not isinstance(value, str):
        raise ValueError("HMAC secret must be a Base64 string")
    try:
        key = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("HMAC secret is not valid Base64") from exc
    if len(key) != 32:
        raise ValueError("HMAC secret must decode to exactly 32 bytes")
    return key
