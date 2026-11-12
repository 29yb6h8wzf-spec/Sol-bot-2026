"""Offline fail-closed checks for dynamic futures universe input contracts."""
import pytest

from signals_v3.dynamic_universe import (
    UniverseObservation, UniverseThresholds, eligibility, select_universe,
)


def observation(symbol="SOLUSDT"):
    return UniverseObservation(
        symbol=symbol,
        observed_at_ms=1000,
        last_price_usd=100.0,
        quote_volume_24h_usd=20_000_000.0,
        spread_bps=2.0,
        bid_depth_10bps_usd=20_000.0,
        ask_depth_10bps_usd=20_000.0,
        min_notional_usd=5.0,
        status="TRADING",
        contract_type="PERPETUAL",
        quote_asset="USDT",
    )


@pytest.mark.parametrize("symbol", [
    "USDT", "solUSDT", "SOLUSDT ", "SOL-USDT", "SOL/USDT",
    "SOLUSDT\\n", "SÓLUSDT", "A" * 31 + "USDT",
])
def test_malformed_symbol_never_enters_research_universe(symbol):
    ok, reason = eligibility(observation(symbol), 1000)
    assert (ok, reason) == (False, "unsupported_market")
    accepted, reasons = select_universe([observation(symbol)], 1000)
    assert accepted == ()
    assert reasons[symbol] == "unsupported_market"


def test_valid_symbol_still_eligible():
    assert eligibility(observation(), 1000) == (True, "eligible")
    assert select_universe([observation()], 1000)[0] == ("SOLUSDT",)


@pytest.mark.parametrize("batch", [None, "", b"", {}, "SOLUSDT"])
def test_invalid_batch_rejected_even_when_empty(batch):
    with pytest.raises(ValueError, match="invalid_universe_observations"):
        select_universe(batch, 1000)
