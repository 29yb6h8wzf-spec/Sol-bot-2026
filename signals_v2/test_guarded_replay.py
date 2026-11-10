"""Static integration tests: exclusion checks execute before replay."""
import unittest
from unittest.mock import patch
from signals_v2.contracts import DataRejected,FIVE_MINUTES_MS
from signals_v2.guarded_replay import guarded_replay

class CandleStub:
    def __init__(self,t):self.open_ms=t
class ProposalStub:
    symbol="SOLUSDT"
def bars(start,count):
    return tuple(CandleStub(start+i*FIVE_MINUTES_MS) for i in range(count))
class GuardedReplayTests(unittest.TestCase):
    def test_rejects_known_bad_candle_before_replay(self):
        feature=bars(300000,64);future=bars(300000+64*FIVE_MINUTES_MS,48)
        intervals={"SOLUSDT":[(feature[0].open_ms,feature[0].open_ms+300000,"ohlcv_disagreement")]}
        with patch("signals_v2.guarded_replay.replay") as mock:
            with self.assertRaisesRegex(DataRejected,"excluded_market_history"):
                guarded_replay(ProposalStub(),feature,future,intervals)
            mock.assert_not_called()
    def test_rejects_missing_full_horizon(self):
        feature=bars(300000,64);future=bars(300000+64*FIVE_MINUTES_MS,47)
        with self.assertRaisesRegex(DataRejected,"incomplete_full_horizon"):
            guarded_replay(ProposalStub(),feature,future,{"SOLUSDT":[]})
    def test_allows_valid_data_to_reach_replay(self):
        feature=bars(300000,64);future=bars(300000+64*FIVE_MINUTES_MS,48)
        with patch("signals_v2.guarded_replay.replay",return_value="REPLAY_CALLED") as mock:
            self.assertEqual(guarded_replay(ProposalStub(),feature,future,{"SOLUSDT":[]}),"REPLAY_CALLED")
            mock.assert_called_once()
if __name__=="__main__":unittest.main()
