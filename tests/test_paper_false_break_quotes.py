import sqlite3
import unittest

from futures_engine import paper_false_break_quotes as q


T = q.STEP * 20


def bars(boundary=T, side="LONG"):
    rows = []
    for i in range(13):
        t = boundary - (13-i)*q.STEP
        rows.append([t,"100","105","95","100","10",t+q.STEP-1,"1000",20,"5"])
    rows[-1][7] = "1500"
    if side == "LONG":
        rows[-1][3], rows[-1][9] = "94", "4"
    elif side == "SHORT":
        rows[-1][2], rows[-1][9] = "106", "6"
    return rows


class TestFrozenRule(unittest.TestCase):
    def test_symmetric_rules_inclusive_volume_and_flow(self):
        for side in ("LONG", "SHORT"):
            rows = bars(side=side)
            self.assertEqual(q.signal(rows,T), side)
            rows[-1][7] = "1499.99"
            self.assertIsNone(q.signal(rows,T))

    def test_reject_double_sweep_no_reclaim_and_insufficient_selling(self):
        for index, value in [(2,"106"),(4,"95"),(9,"4.01")]:
            rows = bars()
            rows[-1][index] = value
            self.assertIsNone(q.signal(rows,T))

    def test_gaps_and_unclosed_bars_are_rejected(self):
        for i in (0,6):
            rows = bars()
            rows[-1][i] += 1
            with self.assertRaises(ValueError):
                q.signal(rows,T)


class TestObservation(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        q.initialize(self.db)
        self.now = T+1000
        self.book = {"symbol":"BTCUSDT","time":self.now-500,"bidPrice":"100","askPrice":"100.1"}
        self.requests = []

    def get(self, path, **params):
        self.requests.append((path, params))
        if path == "klines":
            return bars(boundary=params["endTime"]+1,
                        side="LONG" if params["endTime"]==T-1 else None)
        self.assertEqual(path, "ticker/bookTicker")
        return self.book

    def poll(self):
        q.observe(self.db, "BTCUSDT", clock=lambda:self.now, get=self.get)

    def ledger(self):
        return self.db.execute("SELECT horizon_min,status,bid,ask,reason FROM false_break_quotes "
                               "ORDER BY horizon_min").fetchall()

    def test_observes_four_actual_checkpoints_once_each(self):
        for i in range(4):
            self.now=T+i*q.STEP+1000
            self.book.update(time=self.now-10,bidPrice=str(100+i),askPrice=str(101+i))
            self.poll()
            self.poll()
        self.assertEqual([r[:4] for r in self.ledger()],
                         [(5*i,"OBSERVED",str(100+i),str(101+i)) for i in range(4)])
        self.assertEqual(sum(path=="ticker/bookTicker" for path,_ in self.requests),4)
        self.assertEqual(self.requests[0][1]["endTime"],T-1)
        times=self.db.execute("SELECT received_ms-book_ms FROM false_break_quotes").fetchall()
        self.assertEqual(times,[(10,)]*4)

    def test_downtime_does_not_backfill_quotes(self):
        self.poll()
        self.now=T+3*q.STEP+q.WINDOW+1
        self.poll()
        self.assertEqual(self.ledger()[1:],[(m,"MISSING",None,None,"missed_window")
                                            for m in (5,10,15)])
        self.assertEqual(len(self.requests),2)

    def test_stale_book_never_generates_observed_price(self):
        self.book["time"]=self.now-5000
        self.poll()
        self.assertEqual(self.ledger()[0],(0,"MISSING",None,None,"stale_or_future_book"))

    def test_wrong_symbol_crossed_future_and_late_book(self):
        for changes in ({"symbol":"ETHUSDT"},{"bidPrice":"180"},{"time":self.now+1}):
            self.db.execute("DELETE FROM false_break_quotes")
            self.db.execute("DELETE FROM false_break_scans")
            original=dict(self.book)
            self.book.update(changes)
            self.poll()
            self.assertEqual(self.ledger()[0][1:4],("MISSING",None,None))
            self.book=original

    def test_late_response_cannot_be_labeled_on_time(self):
        def slow_get(path, **params):
            result=self.get(path, **params)
            if path=="ticker/bookTicker":
                self.now += q.WINDOW
            return result
        q.observe(self.db,"BTCUSDT",clock=lambda:self.now,get=slow_get)
        self.assertEqual(self.ledger()[0],(0,"MISSING",None,None,"late_or_reversed_clock"))


if __name__ == "__main__":
    unittest.main()
