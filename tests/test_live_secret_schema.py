import pytest
from live_connection_preflight import credential_pair

@pytest.mark.parametrize("data", [
    {"apiKey": "key", "secret": "token"},
    {"Api": "key", "Secret": "token"},
    {"api_key": "key", "api_secret": "token"},
    {"API_KEY": "key", "API_SECRET": "token"},
    {"BINANCE_API_KEY": "key", "BINANCE_API_SECRET": "token"},
])
def test_accepted_secret_schemas(data):
    assert credential_pair(data) == ("key", "token")

@pytest.mark.parametrize("data", [{}, {"apiKey": "key"}, {"API_KEY": ""}, [], None])
def test_rejects_invalid_schema_without_leaking_values(data):
    with pytest.raises(ValueError, match="secret"):
        credential_pair(data)
