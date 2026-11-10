import unittest
from dataclasses import replace
from signals_v2.contracts import DataRejected
from signals_v3.trend_pullback import ResearchSignal
from signals_v3.pilot_replay import replay_hypothesis,run

class PilotAdapterTests(unittest.TestCase):
    def signal(self):
        return ResearchSignal("SOLUSDT","trend_pullback","LONG",300000,100.,99.,102.)
    def test_adapter_preserves_levels_and_research_lock(self):
        p=replay_hypothesis(self.signal())
        self.assertEqual((p.entry_reference,p.stop_reference,p.target_reference),(100.,99.,102.))
        self.assertTrue(p.research_only)
        self.assertFalse(p.execution_authorized)
    def test_reject_executable_signal(self):
        with self.assertRaisesRegex(DataRejected,"v3_signal_not_research_only"):
            replay_hypothesis(replace(self.signal(),execution_authorized=True))
    def test_reject_invalid_stride_before_file_access(self):
        with self.assertRaisesRegex(ValueError,"invalid_stride"):
            run(None,None,stride=0)
if __name__=="__main__":unittest.main()
