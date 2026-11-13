"""Lazy audit grids must never be accepted as complete historical evidence."""
import unittest
from signals_v3.historical_universe_replay import replay_universe, replay_complete_universe


class MaterializedDecisionGridTests(unittest.TestCase):
    def test_lazy_grid_rejected_before_iteration(self):
        def truncated():
            yield {"decision_ms": 1000, "observations": [], "expected_symbols": []}
            raise OSError("truncated archive")
        for grid in (truncated(), iter(()), (x for x in ())):
            with self.subTest(grid=type(grid).__name__):
                with self.assertRaisesRegex(ValueError, "invalid_historical_decision_container"):
                    replay_universe(grid)

    def test_complete_entrypoint_rejects_lazy_grid(self):
        with self.assertRaisesRegex(ValueError, "invalid_historical_decision_container"):
            replay_complete_universe(iter(()), [1000])

    def test_materialized_empty_grid_retains_existing_error(self):
        for grid in ([], ()):
            with self.subTest(grid=type(grid).__name__):
                with self.assertRaisesRegex(ValueError, "empty_historical_replay"):
                    replay_universe(grid)


if __name__ == "__main__":
    unittest.main()
