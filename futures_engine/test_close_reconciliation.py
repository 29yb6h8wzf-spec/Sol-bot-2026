import ast
import pathlib
import unittest
from unittest.mock import Mock
from futures_engine.close_reconciliation import reconcile_closing

ID = 'vb-XRPUSDT-1795281780000'


def exchange():
    x = Mock()
    x.fapiPrivateV3GetAccount.return_value = {'positions':[], 'totalInitialMargin':'0', 'totalOpenOrderInitialMargin':'0', 'totalMarginBalance':'150'}
    x.fapiPrivateGetOrder.return_value = {'symbol':'XRPUSDT','clientOrderId':ID+'-X','status':'FILLED','origQty':'107.1','executedQty':'107.1','reduceOnly':True}
    x.fapiPrivateGetOpenOrders.return_value = []
    x.fapiPrivateGetOpenAlgoOrders.return_value = {'orders':[]}
    return x


class Reconciliation(unittest.TestCase):
    def test_filled_flat_clean(self):
        x=exchange()
        self.assertEqual(reconcile_closing(x,ID),'closed')
        self.assertEqual(x.fapiPrivateV3GetAccount.call_count,2)
        self.assertTrue(all(c[0].startswith('fapiPrivate') and 'Get' in c[0] for c in x.mock_calls))

    def test_open_position_or_missing_position_response_blocks(self):
        for rows in (None, {}, [{'symbol':'XRPUSDT','positionAmt':'1'}], [{'symbol':'XRPUSDT'}], [{'symbol':'XRPUSDT','positionAmt':'NaN'}]):
            with self.subTest(rows=rows):
                x=exchange();x.fapiPrivateV3GetAccount.return_value['positions']=rows
                self.assertEqual(reconcile_closing(x,ID),'halt_close_unconfirmed')
                x.fapiPrivateGetOrder.assert_not_called()

    def test_invalid_close_proof_blocks(self):
        for k,v in [('status','PARTIALLY_FILLED'),('clientOrderId','other'),('symbol','SOLUSDT'),('reduceOnly',False),('executedQty','100'),('origQty','0'),('origQty','NaN')]:
            with self.subTest(field=k,value=v):
                x=exchange();x.fapiPrivateGetOrder.return_value[k]=v
                self.assertEqual(reconcile_closing(x,ID),'halt_close_unconfirmed')

    def test_leftover_orders_block_without_cancellation(self):
        for method in ('fapiPrivateGetOpenOrders','fapiPrivateGetOpenAlgoOrders'):
            x=exchange();getattr(x,method).return_value=[{'id':'remaining'}]
            self.assertEqual(reconcile_closing(x,ID),'halt_close_cleanup_required')
            x.fapiPrivateDeleteAlgoOrder.assert_not_called()

    def test_second_position_check_blocks_race(self):
        x=exchange();x.fapiPrivateV3GetAccount.side_effect=[{'positions':[], 'totalInitialMargin':'0', 'totalOpenOrderInitialMargin':'0'}, {'positions':[{'positionAmt':'1'}], 'totalInitialMargin':'0', 'totalOpenOrderInitialMargin':'0'}]
        self.assertEqual(reconcile_closing(x,ID),'halt_close_unconfirmed')

    def test_network_error_never_becomes_closed(self):
        x=exchange();x.fapiPrivateGetOrder.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):reconcile_closing(x,ID)

    def test_malformed_order_lists_block(self):
        x=exchange();x.fapiPrivateGetOpenAlgoOrders.return_value={}
        self.assertEqual(reconcile_closing(x,ID),'halt_close_unconfirmed')

    def test_invalid_signal_id_never_calls_exchange(self):
        x=exchange();self.assertEqual(reconcile_closing(x,'bad'),'halt_unresolved_execution');self.assertEqual(x.mock_calls,[])

    def test_runner_marks_only_verified_close_and_returns_before_scanning(self):
        # Load the actual function without importing live engine dependencies.
        source=pathlib.Path(__file__).with_name('breakout_runner.py').read_text()
        tree=ast.parse(source);func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='check_protection')
        ns={'reconcile_closing':reconcile_closing}
        exec(compile(ast.Module(body=[func],type_ignores=[]),'<runner>','exec'),ns)
        journal=Mock();x=exchange()
        self.assertEqual(ns['check_protection'](x,journal,(ID,'CLOSING'),{},0),'reconciled_close')
        journal.mark.assert_called_once_with(ID,'CLOSED');x.create_order.assert_not_called()
        journal.reset_mock();x.fapiPrivateGetOrder.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):ns['check_protection'](x,journal,(ID,'CLOSING'),{},0)
        journal.mark.assert_not_called()

class TickIntegration(unittest.TestCase):
    def test_recovery_tick_cannot_scan_or_submit_a_new_entry(self):
        import sqlite3, time
        from datetime import datetime, timezone
        from decimal import Decimal
        source=pathlib.Path(__file__).with_name('breakout_runner.py').read_text()
        nodes=[n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in ('Journal','check_protection','tick')]
        scan=Mock(side_effect=AssertionError('scanner must not run during recovery'))
        route=Mock(side_effect=AssertionError('entry must not run during recovery'))
        ns=dict(D=Decimal,time=time,datetime=datetime,timezone=timezone,latest_decision=lambda now:now-now%60000,scan=scan,route_breakout=route,reconcile_closing=reconcile_closing)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<runner>','exec'),ns)
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        journal=ns['Journal'](db);journal.claim(ID);journal.mark(ID,'CLOSING')
        x=exchange();x.fetch_time.return_value=time.time_ns()//1000000
        x.fapiPrivateV3GetAccount.return_value={'totalMarginBalance':'150','positions':[], 'totalInitialMargin':'0', 'totalOpenOrderInitialMargin':'0'}
        self.assertEqual(ns['tick'](x,journal),'reconciled_close')
        self.assertEqual(db.execute('SELECT state FROM entries').fetchone()[0],'CLOSED')
        scan.assert_not_called();route.assert_not_called();x.create_order.assert_not_called()


if __name__=='__main__':
    unittest.main()
