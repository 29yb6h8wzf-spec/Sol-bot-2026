import test from "node:test";
import assert from "node:assert/strict";
import handler, {snapshot} from "./feed.mjs";

const slot=1_800_000_000_000;
const receipt={event:"scan_complete",source:"kraken_spot",scheduledTime:slot,recordedAt:slot+4000,
  results:[{symbol:"SOLUSDT",candidates:0,audit:{checks:["BREAKOUT: close=71.91 high12=72.50"]}}],
  failures:[{symbol:"BTCUSDT",reason:"private diagnostic"}]};
test("sorts receipts and leaves absent or mismatched slots empty", async()=>{
  const kv={async get(key){if(typeof key==="string")return receipt;
    return new Map([[key[0],{...receipt,scheduledTime:slot-300000}],[key[1],receipt]]);}};
  const value=await snapshot(kv);
  assert.equal(value.receipts.length,24);
  assert.equal(value.receipts.filter(Boolean).length,2);
  assert.equal(value.receipts[21],null);
  assert.equal(value.receipts[22].slot,slot-300000);
  assert.equal(value.receipts[23].rows[0].price,71.91);
  assert.deepEqual(value.receipts[23].rows[1],{symbol:"BTCUSDT",failed:true,checks:[]});
});
test("unavailable input stays unavailable", async()=>{
  await assert.rejects(snapshot({get:async()=>null}));
});
test("rejects anonymous requests before reading KV", async()=>{
  assert.equal((await handler.fetch(new Request("https://host/v1/scans"),{})).status,403);
});
