import test from 'node:test';
import assert from 'node:assert/strict';
import {SYMBOLS, PAIRS} from './worker.js';
test('all 10 approved markets have unique Kraken pair mappings',()=>{
 assert.equal(SYMBOLS.length,10);
 assert.equal(new Set(SYMBOLS).size,10);
 assert.deepEqual(SYMBOLS,['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','LINKUSDT','LTCUSDT']);
 for(const symbol of SYMBOLS)assert.match(PAIRS[symbol],/^[A-Z]+USDT$/);
});
test('DOGE uses Kraken XDG symbol',()=>assert.equal(PAIRS.DOGEUSDT,'XDGUSDT'));
