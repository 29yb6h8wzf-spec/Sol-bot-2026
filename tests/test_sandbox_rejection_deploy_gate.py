import unittest
from futures_engine.sandbox_rejection_deploy_gate import assess

ALL = dict(ci_passed=True, consumer_source_reviewed=True,
           sandbox_queue_verified=True, durable_audit_tested=True,
           mock_sqs_tested=True, rollback_backup_verified=True,
           paper_only=True, dlq_replay_disabled=True)

class GateTests(unittest.TestCase):
    def test_all_requirements_allow_gate(self):
        self.assertTrue(assess(**ALL).ready)

    def test_every_requirement_blocks_individually(self):
        for field in ALL:
            with self.subTest(field=field):
                values = dict(ALL, **{field: False})
                self.assertFalse(assess(**values).ready)
                self.assertEqual(len(assess(**values).blockers), 1)

    def test_multiple_blockers_reported(self):
        values = dict(ALL, ci_passed=False, mock_sqs_tested=False)
        self.assertEqual(len(assess(**values).blockers), 2)

if __name__ == "__main__":
    unittest.main()
