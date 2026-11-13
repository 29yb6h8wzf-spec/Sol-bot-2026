import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from signals_v3.dynamic_universe import UniverseObservation
from signals_v3.historical_universe_replay import replay_universe,replay_complete_universe
from signals_v3.historical_universe_gate import load_snapshots,verify_decision_snapshot,COLUMNS

class HistoricalUniverseGateTests(unittest.TestCase):
    def setUp(self):
        self.now=1_000_000
        self.obs=UniverseObservation("ADAUSDT",self.now,1.25,25_000_000,3,20_000,22_000,5,"TRADING","PERPETUAL","USDT")
    def test_malformed_listing_container_fails_closed(self):
        for listing in ("ADAUSDT", b"ADAUSDT", {"ADAUSDT": 1}, {"ADAUSDT"}, None, 17):
            with self.subTest(listing=repr(listing)):
                with self.assertRaisesRegex(ValueError,"invalid_historical_market_listing|missing_historical_market_listing"):
                    verify_decision_snapshot([self.obs],self.now,listing)
    def test_lazy_historical_listings_fail_closed(self):
        def failing_listing():
            yield "ADAUSDT"
            raise OSError("historical listing stream truncated")
        for listing in ((s for s in ("ADAUSDT",)), failing_listing(), iter(("ADAUSDT",))):
            with self.subTest(listing=type(listing).__name__):
                with self.assertRaisesRegex(ValueError, "invalid_historical_market_listing"):
                    verify_decision_snapshot([self.obs], self.now, listing)
    def test_materialized_historical_listing_remains_valid(self):
        for listing in (["ADAUSDT"], ("ADAUSDT",)):
            with self.subTest(container=type(listing).__name__):
                self.assertEqual(verify_decision_snapshot([self.obs], self.now, listing)["eligible_symbols"], ("ADAUSDT",))
    def test_unhashable_and_malformed_listing_entries_fail_closed(self):
        for listing in ([["ADAUSDT"]], [{"symbol": "ADAUSDT"}], [None], [17], [b"ADAUSDT"], ["SOLBTC"]):
            with self.subTest(listing=repr(listing)):
                with self.assertRaisesRegex(ValueError, "invalid_historical_market_listing"):
                    verify_decision_snapshot([self.obs], self.now, listing)
    def test_malformed_observation_fails_closed(self):
        for observations in ([None], [object()], ["ADAUSDT"], {"ADAUSDT": self.obs}):
            with self.subTest(observations=repr(observations)):
                with self.assertRaisesRegex(ValueError,"invalid_historical_universe_observations"):
                    verify_decision_snapshot(observations,self.now,["ADAUSDT"])
    def test_nonsequence_observations_fail_closed(self):
        for observations in (17, object(), {"ADAUSDT"}, frozenset({"ADAUSDT"}), (x for x in [self.obs])):
            with self.subTest(observations=repr(observations)):
                with self.assertRaisesRegex(ValueError,"invalid_historical_universe_observations"):
                    verify_decision_snapshot(observations,self.now,["ADAUSDT"])
    def test_ordered_tuple_observations_accepted(self):
        self.assertEqual(verify_decision_snapshot((self.obs,),self.now,("ADAUSDT",))["eligible_symbols"],("ADAUSDT",))
    def test_invalid_decision_timestamps_fail_closed(self):
        for timestamp in (None, True, False, -1, 1.0, "1000000", [], {}):
            with self.subTest(timestamp=repr(timestamp)):
                with self.assertRaisesRegex(ValueError, "invalid_decision_timestamp"):
                    verify_decision_snapshot([self.obs], timestamp, ["ADAUSDT"])

    def test_complete_snapshot_eligible(self):
        r=verify_decision_snapshot([self.obs],self.now,["ADAUSDT"])
        self.assertEqual(r["eligible_symbols"],("ADAUSDT",))
    def test_missing_listing_rejected(self):
        with self.assertRaisesRegex(ValueError,"missing_historical_market_listing"):
            verify_decision_snapshot([self.obs],self.now)
    def test_incomplete_listing_rejected(self):
        with self.assertRaisesRegex(ValueError,"incomplete_historical_universe"):
            verify_decision_snapshot([self.obs],self.now,["ADAUSDT","SOLUSDT"])
    def test_duplicate_listing_rejected(self):
        with self.assertRaisesRegex(ValueError,"invalid_historical_market_listing"):
            verify_decision_snapshot([self.obs],self.now,["ADAUSDT","ADAUSDT"])
    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate_symbol_snapshot"):
            verify_decision_snapshot([self.obs,self.obs],self.now,["ADAUSDT"])
    def test_future_snapshot_cannot_qualify(self):
        obs=replace(self.obs,observed_at_ms=self.now+1)
        r=verify_decision_snapshot([obs],self.now,["ADAUSDT"])
        self.assertEqual(r["eligible_symbols"],())
    def test_stale_snapshot_cannot_qualify(self):
        obs=replace(self.obs,observed_at_ms=self.now-60_001)
        r=verify_decision_snapshot([obs],self.now,["ADAUSDT"])
        self.assertEqual(r["eligible_symbols"],())
    def test_price_boundaries(self):
        for price,eligible in ((0.98,False),(0.99,True),(150.0,True),(150.01,False)):
            with self.subTest(price=price):
                obs=replace(self.obs,last_price_usd=price)
                r=verify_decision_snapshot([obs],self.now,["ADAUSDT"])
                self.assertEqual(bool(r["eligible_symbols"]),eligible)
    def test_replay_market_enters_price_band(self):
        early=replace(self.obs,last_price_usd=0.98)
        later=replace(self.obs,observed_at_ms=self.now+60_000,last_price_usd=1.00)
        result=replay_universe([
            {"decision_ms":self.now,"observations":[early],"expected_symbols":["ADAUSDT"]},
            {"decision_ms":self.now+60_000,"observations":[later],"expected_symbols":["ADAUSDT"]},
        ])
        self.assertEqual(result[0]["eligible_symbols"],())
        self.assertEqual(result[1]["eligible_symbols"],("ADAUSDT",))
    def test_replay_rejects_lazy_historical_listings(self):
        def truncated_listing():
            yield "ADAUSDT"
            raise OSError("historical listing stream truncated")
        for listing in ((x for x in ("ADAUSDT",)), iter(("ADAUSDT",)), truncated_listing()):
            with self.subTest(kind=type(listing).__name__):
                decision={"decision_ms":self.now,"observations":[self.obs],
                          "expected_symbols":listing}
                with self.assertRaisesRegex(ValueError,"invalid_historical_market_listing"):
                    replay_universe([decision],expected_decision_times=[self.now])
    def test_replay_accepts_materialized_historical_listings(self):
        for listing in (["ADAUSDT"],("ADAUSDT",)):
            decision={"decision_ms":self.now,"observations":[self.obs],
                      "expected_symbols":listing}
            result=replay_universe([decision],expected_decision_times=[self.now])
            self.assertEqual(result[0]["eligible_symbols"],("ADAUSDT",))
    def test_replay_tracks_listings_entering_and_leaving(self):
        second=replace(self.obs,symbol="SOLUSDT",observed_at_ms=self.now+60_000)
        result=replay_universe([
            {"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]},
            {"decision_ms":self.now+60_000,"observations":[second],"expected_symbols":["SOLUSDT"]},
        ])
        self.assertEqual(result[1]["listed_added"],("SOLUSDT",))
        self.assertEqual(result[1]["listed_removed"],("ADAUSDT",))
    def test_complete_replay_requires_schedule(self):
        item={"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]}
        with self.assertRaisesRegex(ValueError,"missing_expected_decision_schedule"):
            replay_complete_universe([item],None)
    def test_replay_rejects_lazy_expected_schedule(self):
        item={"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]}
        def truncated_schedule():
            yield self.now
            raise OSError("truncated historical schedule")
        for schedule in ((x for x in [self.now]), iter([self.now]), truncated_schedule(), "1000000", {self.now}):
            with self.subTest(kind=type(schedule).__name__):
                with self.assertRaisesRegex(ValueError,"invalid_expected_decision_schedule"):
                    replay_universe([item],expected_decision_times=schedule)
    def test_replay_accepts_materialized_expected_schedule(self):
        item={"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]}
        for schedule in ([self.now],(self.now,)):
            self.assertEqual(len(replay_complete_universe([item],schedule)),1)
    def test_verified_replay_rejects_lazy_schedule_before_manifest_io(self):
        from unittest.mock import patch
        from signals_v3.historical_universe_replay import replay_verified_historical_universe
        item={"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]}
        def truncated_schedule():
            yield self.now
            raise OSError("historical schedule truncated")
        for schedule in ((x for x in [self.now]), iter([self.now]), truncated_schedule(), "1000000", {self.now}):
            with self.subTest(kind=type(schedule).__name__):
                with patch("signals_v3.historical_evidence_provenance.verify_historical_evidence_manifest") as verify:
                    with self.assertRaisesRegex(ValueError,"invalid_expected_decision_schedule"):
                        replay_verified_historical_universe([item],schedule,"unused-manifest.json")
                    verify.assert_not_called()
    def test_verified_replay_materialized_schedule_reaches_evidence_gate(self):
        from unittest.mock import patch
        from signals_v3.historical_universe_replay import replay_verified_historical_universe
        item={"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]}
        for schedule in ([self.now],(self.now,)):
            with self.subTest(kind=type(schedule).__name__):
                with patch("signals_v3.historical_evidence_provenance.verify_historical_evidence_manifest",return_value={"historical_evidence_verified":False}) as verify:
                    with self.assertRaisesRegex(ValueError,"unverified_historical_evidence"):
                        replay_verified_historical_universe([item],schedule,"unused-manifest.json")
                    verify.assert_called_once_with("unused-manifest.json",self.now)
    def test_replay_explicit_schedule_rejects_gap(self):
        item={"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]}
        with self.assertRaisesRegex(ValueError,"incomplete_historical_decision_schedule"):
            replay_universe([item],expected_decision_times=[self.now,self.now+60_000])
    def test_replay_explicit_schedule_accepts_complete_series(self):
        later=replace(self.obs,observed_at_ms=self.now+60_000)
        result=replay_universe([
            {"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]},
            {"decision_ms":self.now+60_000,"observations":[later],"expected_symbols":["ADAUSDT"]},
        ],expected_decision_times=[self.now,self.now+60_000])
        self.assertEqual(len(result),2)
    def test_replay_missing_period_rejected(self):
        with self.assertRaisesRegex(ValueError,"missing_historical_evidence"):
            replay_universe([{"decision_ms":self.now}])
    def test_replay_out_of_order_rejected(self):
        item={"decision_ms":self.now,"observations":[self.obs],"expected_symbols":["ADAUSDT"]}
        with self.assertRaisesRegex(ValueError,"nonmonotonic_decision_times"):
            replay_universe([item,item])
    def test_csv_duplicate_header_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"snap.csv"
            p.write_text(",".join(COLUMNS+("symbol",))+"\n")
            with self.assertRaisesRegex(ValueError,"invalid_universe_snapshot_schema"):
                load_snapshots(p)
    def test_csv_invalid_numeric_and_extra_column_rejected(self):
        for field,value in (("last_price_usd","nan"),("spread_bps","inf"),("bid_depth_10bps_usd","-1"),("observed_at_ms","not-a-time")):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                p=Path(directory)/"snap.csv"
                values={k:str(getattr(self.obs,k)) for k in COLUMNS}
                values[field]=value
                p.write_text(",".join(COLUMNS)+"\n"+",".join(values[k] for k in COLUMNS)+"\n")
                with self.assertRaisesRegex(ValueError,"invalid_universe_snapshot_row"):
                    load_snapshots(p)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"snap.csv"
            p.write_text(",".join(COLUMNS)+"\n"+",".join(str(getattr(self.obs,k)) for k in COLUMNS)+",unexpected\n")
            with self.assertRaisesRegex(ValueError,"invalid_universe_snapshot_row"):
                load_snapshots(p)
    def test_csv_rejects_noncanonical_or_negative_timestamps(self):
        for timestamp in ("-1", "+1000000", "001000000", "1.0", " 1000000"):
            with self.subTest(timestamp=timestamp), tempfile.TemporaryDirectory() as directory:
                p=Path(directory)/"snap.csv"
                values={k:str(getattr(self.obs,k)) for k in COLUMNS}
                values["observed_at_ms"]=timestamp
                p.write_text(",".join(COLUMNS)+"\n"+",".join(values[k] for k in COLUMNS)+"\n")
                with self.assertRaisesRegex(ValueError,"invalid_universe_snapshot_row"):
                    load_snapshots(p)
    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"snap.csv"
            p.write_text(",".join(COLUMNS)+"\n"+",".join(str(getattr(self.obs,k)) for k in COLUMNS)+"\n")
            self.assertEqual(load_snapshots(p),(self.obs,))
if __name__=="__main__":unittest.main()
