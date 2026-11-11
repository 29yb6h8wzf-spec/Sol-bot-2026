"""Offline contract tests for malformed dynamic-universe batches."""
import unittest

from signals_v3.dynamic_universe import select_universe, UniverseThresholds


class DynamicUniverseBatchContractTests(unittest.TestCase):
    def test_non_iterable_batches_fail_closed(self):
        for value in (0, 1.5, False, object()):
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, "invalid_universe_observations"):
                    select_universe(value, 1000)

    def test_empty_valid_iterable_is_not_a_market_evidence_claim(self):
        for value in ([], (), iter(())):
            with self.subTest(kind=type(value).__name__):
                selected, reasons = select_universe(value, 1000)
                self.assertEqual(selected, ())
                self.assertEqual(reasons, {})

    def test_invalid_config_rejected_before_iterating_empty_batch(self):
        limits = UniverseThresholds(max_observation_age_ms=-1)
        with self.assertRaisesRegex(ValueError, "invalid_universe_thresholds"):
            select_universe(iter(()), 1000, limits)


if __name__ == "__main__":
    unittest.main()
