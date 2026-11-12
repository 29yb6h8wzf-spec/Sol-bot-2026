import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzePriceWindow} from './copytrading-price-window.mjs';
const base={source:'binance',portfolioAlias:'sample',evidenceType:'closed_trade_export',startingCapitalUsdt:1000};
const trade=(id,price,evidence='exchange_execution_export')=>({tradeId:id,symbol:'SOLUSDT',side:'LONG',openedAt:'2026-01-01T00:00:00Z',closedAt:'2026-01-01T01:00:00Z',netPnlUsdt:2,entryPriceUsdt:price,entryPriceEvidence:evidence});
test('filters historical entry price inclusively, never current price',()=>{
 const result=analyzePriceWindow([{...base,closedTrades:[trade('a',0.99),trade('b',150),trade('c',0.98),trade('d',151)]}]);
 assert.equal(result.acceptedTrades,2);
 assert.equal(result.result.portfolios[0].closedTrades,2);
 assert.equal(result.exclusions.length,2);
 assert.equal(result.executionAuthorized,false);
 assert.equal(result.profitabilityProven,false);
});
test('rejects missing and unverified price evidence',()=>{
 const result=analyzePriceWindow([{...base,closedTrades:[trade('a',2,'ticker_snapshot'),trade('b',undefined)]}]);
 assert.equal(result.acceptedTrades,0);
 assert.equal(result.result,null);
 assert.deepEqual(result.exclusions.map(x=>x.reason),['unverified_entry_price_source','missing_verified_historical_entry_price']);
});
test('rejects invalid price window',()=>{
 assert.throws(()=>analyzePriceWindow([{...base,closedTrades:[trade('a',2)]}],{minPrice:150,maxPrice:0.99}),/Invalid price range/);
});
