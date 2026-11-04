"""Fail-closed regression: registry must be a regular file, not a symlink."""
import pytest
from demo_trade_attribution import registry_orders


def test_symlink_to_missing_registry_is_rejected(tmp_path):
    link = tmp_path / "registry.json"
    link.symlink_to(tmp_path / "not-created.json")
    with pytest.raises(ValueError, match="untrusted_registry_symlink"):
        registry_orders(link)


def test_symlink_to_existing_registry_is_rejected(tmp_path):
    target = tmp_path / "registry-real.json"
    target.write_text("{}")
    target.chmod(0o600)
    link = tmp_path / "registry.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="untrusted_registry_symlink"):
        registry_orders(link)


def test_missing_registry_does_not_infer_ownership(tmp_path):
    orders, present = registry_orders(tmp_path / "not-created.json")
    assert orders == {}
    assert present is False
