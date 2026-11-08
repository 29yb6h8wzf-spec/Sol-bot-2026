"""Offline integration tests for read-only demo signal planning."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal as D

from futures_engine.offline_plan_replay import replay

from demo_plan_bridge import build_plan, exchange_filters, journal_inbox, verify_and_plan
from demo_risk_adapter import preflight, preflight_with_monitor
from demo_signal_router import connect_inbox, evaluate

CANDLE = 4500000
NOW = CANDLE + 300000 + 30000
BARS = [[CANDLE - (15-i)*300000, 100, 101, 99, 100, 10] for i in range(16)]


def payload():
    return {"signal_id": "s1", "symbol": "XRPUSDT", "direction": "long",
            "timestamp": NOW // 1000 - 10}


def verified(payload, *, now):
    return {"signal_id": payload["signal_id"], "symbol": "XRP/USDT:USDT",
            "source": "verified_85_score_engine", "score": 90,
            "direction": "long", "closed_5m_candle_ms": CANDLE,
            "verification": {"status": "RECALCULATED_RESEARCH_CANDIDATE",
                             "score_verified_independently": True,
                             "execution_authorized": False}}


def market():
    return {"symbol": "XRP/USDT:USDT", "swap": True, "linear": True,
            "info": {"filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ]}}


class Exchange:
    def __init__(self):
        self.closed = False
    def close(self):
        self.closed = True


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.exchange = Exchange()
    def loader(self, symbol, timeframe):
        self.assertEqual((symbol, timeframe), ("XRP/USDT:USDT", "5m"))
        return self.exchange, market(), BARS

    def test_valid_plan_includes_fee_buffer_and_never_executes(self):
        p = build_plan(payload(), verifier=verified, loader=self.loader, now_ms=NOW)
        self.assertEqual(p["status"], "INDICATIVE_PLAN_ONLY_NOT_EXECUTABLE")
        self.assertFalse(p["orders_sent"])
        self.assertFalse(p["execution_authorized"])
        self.assertTrue(self.exchange.closed)
        self.assertLessEqual(float(p["estimated_loss_including_buffer"]), 1.50)
        self.assertLessEqual(float(p["estimated_notional"]), 300)

    def test_plans_cover_adverse_fills_and_both_fees(self):
        for side in ("long", "short"):
            with self.subTest(side=side):
                def verifier(p, *, now):
                    return {**verified(p, now=now), "direction": side}
                p = build_plan({**payload(), "direction": side}, verifier=verifier,
                               loader=self.loader, now_ms=NOW)
                sign = 1 if side == "long" else -1
                fill = D(p["entry"]) * (1 + sign * D("0.0005"))
                exit_fill = D(p["stop"]) * (1 - sign * D("0.0005"))
                loss = abs(fill - exit_fill) + (fill + exit_fill) * D("0.0006")
                self.assertLessEqual(loss * D(p["quantity"]), D(p["estimated_loss_including_buffer"]))
                self.assertLessEqual(D(p["estimated_loss_including_buffer"]), D("1.50"))
                next_open = CANDLE + 300000
                outcome = replay({**p, "closed_5m_candle_ms": next_open},
                                 [[next_open, 100, 104, 96, 100]],
                                 fee_rate="0.0006", slippage_rate="0.0005")
                self.assertEqual(outcome.get("exit_reason"), "STOP")

    def test_long_notional_cap_covers_adverse_entry_price(self):
        narrow = [[b[0], 100, 100, 100, 100, 10] for b in BARS]
        p = build_plan(payload(), verifier=verified, now_ms=NOW,
                       loader=lambda *_: (self.exchange, market(), narrow))
        self.assertLessEqual(D(p["quantity"]) * D("100.05"), D("300"))

    def test_stale_signal_never_fetches_market(self):
        p = payload()
        p["timestamp"] -= 121
        with self.assertRaisesRegex(ValueError, "signal_stale_or_future"):
            build_plan(p, verifier=verified, loader=self.loader, now_ms=NOW)
        self.assertFalse(self.exchange.closed)

    def test_bad_exchange_filters_fail_closed(self):
        m = market()
        m["info"]["filters"].pop()
        with self.assertRaisesRegex(ValueError, "exchange_filters_missing"):
            exchange_filters(m)

    def test_candle_mismatch_fails_and_closes_exchange(self):
        def wrong(symbol, timeframe):
            return self.exchange, market(), [[b[0]-300000, *b[1:]] for b in BARS]
        with self.assertRaisesRegex(ValueError, "verified_candle_mismatch"):
            build_plan(payload(), verifier=verified, loader=wrong, now_ms=NOW)
        self.assertTrue(self.exchange.closed)

    def test_independent_verification_required(self):
        def invalid(payload, *, now):
            v = verified(payload, now=now)
            v["verification"] = {}
            return v
        with self.assertRaisesRegex(ValueError, "independent_proof_required"):
            build_plan(payload(), verifier=invalid, loader=self.loader, now_ms=NOW)
        self.assertTrue(self.exchange.closed)

    def test_router_plans_preflights_and_claims_only_once(self):
        def independent(message, *, now):
            return {**verified(message, now=now), "strategy": "MACD_VOLUME"}

        def planner(message):
            return verify_and_plan(message, verifier=independent, loader=self.loader, now_ms=NOW)

        message = {**payload(), "entry": "999", "quantity": "999"}
        intent = planner(message)
        self.assertEqual(float(intent["entry"]), 100)
        self.assertFalse(intent["execution_authorized"])
        self.assertFalse(intent["risk_snapshot_approved"])
        self.assertFalse(intent["orders_sent"])
        account = {"equity": "150", "day_start": "150", "used_margin": "0", "open_risk": "0"}
        # Leave headroom for the unbuffered stop loss, but not for its costs.
        raw_risk = D(intent["quantity"]) * abs(D(intent["entry"]) - D(intent["stop"]))
        headroom = (raw_risk + D(intent["estimated_loss_including_buffer"])) / 2
        tight = {**account, "open_risk": str(D("7.5") - headroom)}
        self.assertEqual(preflight(intent, tight), (False, "portfolio_risk_budget"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def monitored(v, a):
                return preflight_with_monitor(v, a, status_path=root/"absent", now=NOW // 1000)
            self.assertEqual(evaluate(message, verifier=planner, preflight=monitored,
                                      account=account, now=NOW // 1000),
                             ("REJECTED_RISK", "risk_monitor_status_missing"))
            with sqlite3.connect(root/"inbox") as db:
                db.execute("CREATE TABLE signals(signal_id TEXT PRIMARY KEY, payload TEXT, received_at INTEGER)")
                for sid in ("s1", "s2"):
                    db.execute("INSERT INTO signals VALUES(?,?,?)",
                               (sid, json.dumps({**message, "signal_id": sid}), NOW // 1000))
            results = connect_inbox(root/"inbox", root/"routes", verifier=planner,
                                    preflight=preflight, account=account, now=NOW // 1000)
            self.assertEqual([r["status"] for r in results],
                             ["DEMO_ELIGIBLE_NOT_SUBMITTED", "REJECTED_DUPLICATE"])
            self.assertTrue(all(r["orders_sent"] is False for r in results))

    def test_journal_idempotent_and_no_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox.sqlite3"
            journal = Path(tmp) / "plans.sqlite3"
            with sqlite3.connect(inbox) as db:
                db.execute("CREATE TABLE signals(signal_id TEXT PRIMARY KEY, payload TEXT, received_at INTEGER)")
                db.execute("INSERT INTO signals VALUES (?,?,?)",
                           ("s1", json.dumps(payload()), NOW // 1000))
            def offline(p, *, now_ms):
                return build_plan(p, verifier=verified, loader=self.loader, now_ms=now_ms)
            first = journal_inbox(inbox, journal, planner=offline, now_ms=NOW)
            self.assertEqual(first[0]["status"], "PLANNED_ONLY")
            self.assertFalse(first[0]["orders_sent"])
            self.assertEqual(journal_inbox(inbox, journal, planner=offline, now_ms=NOW), [])
            with sqlite3.connect(journal) as db:
                plan_json = json.loads(db.execute("SELECT plan_json FROM demo_plans").fetchone()[0])
                self.assertFalse(plan_json["execution_authorized"])

if __name__ == "__main__":
    unittest.main()
