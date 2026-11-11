"""Offline regression for fail-closed empty dynamic-universe scans."""
import pytest

from signals_v3.dynamic_universe import UniverseThresholds, select_universe


@pytest.mark.parametrize("limits", [
    None,
    UniverseThresholds(max_spread_bps=float("nan")),
    UniverseThresholds(min_quote_volume_24h_usd=float("inf")),
    UniverseThresholds(max_observation_age_ms=-1),
    UniverseThresholds(available_notional_usd=-1),
    UniverseThresholds(max_observation_age_ms=True),
])
def test_empty_scan_rejects_invalid_configuration(limits):
    with pytest.raises(ValueError, match="invalid_universe_thresholds"):
        select_universe([], 1000, limits)


@pytest.mark.parametrize("decision_ms", [-1, True, 1.0, "1000"])
def test_empty_scan_rejects_invalid_decision_timestamp(decision_ms):
    with pytest.raises(ValueError, match="invalid_decision_timestamp"):
        select_universe([], decision_ms)


def test_empty_scan_with_valid_configuration_is_empty():
    assert select_universe([], 1000) == ((), {})
