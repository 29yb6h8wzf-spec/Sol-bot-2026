import assert from "node:assert/strict";
import { test } from "node:test";
import { webcrypto } from "node:crypto";
import { handleBinanceResearch, validateBinanceResearchEnvelope } from "../cloudflare/binance_research_ingest.js";

globalThis.crypto ||= webcrypto;
const secret = "test-only-bridge-secret-32-bytes-abcdefgh";
const URL = "https://sol-bot-2026.29yb6h8wzf.workers.dev/internal/binance-research";
const now = Math.floor(Date.now() / 1000);
const payload = {
  type: "SIGNALPILOT_BINANCE_RESEARCH_V1",
  signal_id: "r-0123456789abcdef01234567",
  symbol: "SOLUSDT", direction: "long", score: 85,
  timestamp: now - 20, source: "verified_85_score_engine",
  execution_authorized: false, orders_sent: false
};

async function signedRequest(data=payload, stamp=now, key=secret) {
  const raw = JSON.stringify(data);
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    "raw", enc.encode(key), {name: "HMAC", hash: "SHA-256"}, false, ["sign"]);
  const signed = new Uint8Array(await crypto.subtle.sign(
    "HMAC", cryptoKey, enc.encode(String(stamp) + "." + raw)));
  const signature = [...signed].map(x => x.toString(16).padStart(2, "0")).join("");
  return new Request(URL, {
    method: "POST", body: raw,
    headers: {"x-signalpilot-timestamp": String(stamp),
              "x-signalpilot-signature": signature}
  });
}

function environment() {
  const values = new Map();
  return {
    BINANCE_RESEARCH_INGEST_SECRET: secret,
    TELEGRAM_CHAT_ID: "12345",
    SIGNAL_STATE: {
      async get(k) { return values.get(k) || null; },
      async put(k, v) { values.set(k, v); }
    }
  };
}

test("owner-only valid research delivery, no order", async () => {
  let delivered = [];
  const r = await handleBinanceResearch(await signedRequest(), environment(), {
    sendOwner: async (env, id, message) => delivered.push({id, message})
  });
  assert.equal(r.status, 200);
  assert.equal(delivered.length, 1);
  assert.equal(delivered[0].id, "12345");
  assert.match(delivered[0].message, /מחקר/);
  assert.doesNotMatch(delivered[0].message, /כניסה: \$/);
});

test("dedup prevents repeated delivery", async () => {
  const env = environment();
  let calls = 0;
  const opts = {sendOwner: async () => { calls++; }};
  await handleBinanceResearch(await signedRequest(), env, opts);
  const r = await handleBinanceResearch(await signedRequest(), env, opts);
  assert.equal((await r.json()).status, "already_claimed");
  assert.equal(calls, 1);
});

test("wrong signature rejected", async () => {
  const r = await handleBinanceResearch(
    await signedRequest(payload, now, "attacker-key-32-bytes-abcdefghijkl"), environment(),
    {sendOwner: async () => { throw Error("must not send"); }});
  assert.equal(r.status, 401);
});

test("stale signed payload rejected", async () => {
  const r = await handleBinanceResearch(
    await signedRequest({...payload, timestamp: now - 200}), environment(),
    {sendOwner: async () => { throw Error("must not send"); }});
  assert.equal(r.status, 422);
});

test("replayed old timestamp rejected", async () => {
  const r = await handleBinanceResearch(
    await signedRequest(payload, now - 200), environment(),
    {sendOwner: async () => { throw Error("must not send"); }});
  assert.equal(r.status, 401);
});

test("no shared secret disables route", async () => {
  const env = environment();
  delete env.BINANCE_RESEARCH_INGEST_SECRET;
  const r = await handleBinanceResearch(await signedRequest(), env);
  assert.equal(r.status, 503);
});

test("cannot enable orders in payload", () => {
  assert.throws(() => validateBinanceResearchEnvelope(
    {...payload, orders_sent: true}, now), /invalid_or_stale/);
});

test("cannot add executable price or order fields", () => {
  assert.throws(() => validateBinanceResearchEnvelope(
    {...payload, entry: 100}, now), /invalid_envelope/);
});

test("below 85 rejected", () => {
  assert.throws(() => validateBinanceResearchEnvelope(
    {...payload, score: 84}, now), /invalid_or_stale/);
});

test("ambiguous Telegram delivery never auto retries", async () => {
  const env = environment();
  let calls = 0;
  const opts = {sendOwner: async () => { calls++; throw Error("ambiguous"); }};
  const r1 = await handleBinanceResearch(await signedRequest(), env, opts);
  const r2 = await handleBinanceResearch(await signedRequest(), env, opts);
  assert.equal(r1.status, 502);
  assert.equal((await r2.json()).status, "already_claimed");
  assert.equal(calls, 1);
});

test("other path does not invoke bridge", async () => {
  const r = await handleBinanceResearch(
    new Request("https://sol-bot-2026.29yb6h8wzf.workers.dev/"), environment());
  assert.equal(r.status, 404);
});

test("explicit signed test delivers only clearly labeled test message to owner", async () => {
  const env = environment();
  const testPayload = {
    type: "SIGNALPILOT_BINANCE_BRIDGE_TEST_V1",
    nonce: "test-0123456789abcdef01234567",
    timestamp: now,
    execution_authorized: false,
    orders_sent: false
  };
  let sent = [];
  const opts = {sendOwner: async (e, id, msg) => sent.push({id, msg})};
  const r1 = await handleBinanceResearch(await signedRequest(testPayload), env, opts);
  const r2 = await handleBinanceResearch(await signedRequest(testPayload), env, opts);
  assert.equal(r1.status, 200);
  assert.equal((await r1.json()).test_only, true);
  assert.equal((await r2.json()).status, "already_claimed");
  assert.equal(sent.length, 1);
  assert.equal(sent[0].id, "12345");
  assert.match(sent[0].msg, /בדיקה בלבד/);
  assert.doesNotMatch(sent[0].msg, /SOLUSDT|LONG|SHORT/);
});

test("test mode cannot be used to authorize orders", async () => {
  const testPayload = {
    type: "SIGNALPILOT_BINANCE_BRIDGE_TEST_V1",
    nonce: "test-0123456789abcdef01234567",
    timestamp: now,
    execution_authorized: true,
    orders_sent: false
  };
  const r = await handleBinanceResearch(await signedRequest(testPayload), environment(),
    {sendOwner: async () => {throw Error("must not deliver");}});
  assert.equal(r.status, 422);
});
