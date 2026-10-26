import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluateSetup} from './risk-engine.mjs';
test('sizes using loss plus estimated costs',()=>{
 const r=evaluateSetup({direction:'SHORT',entry:1.2948,stop:1.3057,target:1.2759,leverage:4});
 assert.ok(Math.abs(r.expectedLoss-1.5)<1e-8);
 assert.equal(r.eligible,false);
 assert.ok(r.expectedProfit<5);
});
test('does not make risk smaller when leverage increases',()=>{
 const base={direction:'LONG',entry:100,stop:99,target:110};
 const a=evaluateSetup({...base,leverage:2});
 const b=evaluateSetup({...base,leverage:4});
 assert.equal(a.notional,b.notional);
 assert.equal(a.expectedLoss,b.expectedLoss);
 assert.equal(a.margin,2*b.margin);
});
test('rejects inverted target',()=>assert.equal(evaluateSetup({direction:'LONG',entry:100,stop:99,target:98}).eligible,false));
test('rejects insufficient margin',()=>assert.equal(evaluateSetup({direction:'LONG',entry:100,stop:99,target:110,availableMargin:1}).eligible,false));
