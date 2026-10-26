import test from 'node:test';
import assert from 'node:assert/strict';
import {formatScanStatus} from './worker.js';
const now=Date.UTC(2026,9,26,18,10);
const makeBars=(count,period)=>Array.from({length:count},(_,i)=>({time:now-(count-i)*period,open:100+i*.01,close:100+i*.01,high:100.2+i*.01,low:99.8+i*.01,volume:100}));
const five=makeBars(120,300000),four=makeBars(100,14400000);
test('5-minute status displays entry SL and TP for a long setup',()=>{
 const message=formatScanStatus('SOLUSDT',five,four,[{strategy:'BREAKOUT',direction:'LONG',entry:100,stop:99.5}],now);
 assert.match(message,/SL: \$99\.50000/);
 assert.match(message,/TP \(2R\): \$101\.00000/);
 assert.match(message,/כניסה: \$100\.00000/);
});
test('short setups use the correct TP direction',()=>{
 const message=formatScanStatus('XRPUSDT',five,four,[{strategy:'EMA_ADX',direction:'SHORT',entry:100,stop:100.5}],now);
 assert.match(message,/SL: \$100\.50000/);
 assert.match(message,/TP \(2R\): \$99\.00000/);
});
test('no setup does not show fictional levels',()=>{
 const message=formatScanStatus('SOLUSDT',five,four,[],now);
 assert.doesNotMatch(message,/TP \(2R\):/);
 assert.match(message,/אין כניסה/);
});
