import {liveRoute} from "./live.mjs";
const PERIOD = 300_000;
const symbols = new Set(["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]);

function count(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function normalize(receipt) {
  if (receipt?.event !== "scan_complete" || receipt.source !== "kraken_spot" ||
      !Number.isSafeInteger(receipt.scheduledTime) || !Number.isSafeInteger(receipt.recordedAt) ||
      !Array.isArray(receipt.results) || !Array.isArray(receipt.failures)) return null;
  const rows = [];
  for (const item of receipt.results) {
    if (!symbols.has(item.symbol)) continue;
    const checks = (Array.isArray(item.audit?.checks) ? item.audit.checks : [])
      .filter(x => typeof x === "string").slice(0, 12).map(x => x.slice(0, 450));
    const breakout = checks.find(x => x.startsWith("BREAKOUT"));
    const match = breakout?.match(/\bclose=(\d+(?:\.\d+)?)(?:\s|$)/);
    rows.push({symbol: item.symbol, candle: item.candle || null, price: match ? Number(match[1]) : null,
      candidates: count(item.candidates), delivered: count(item.audit?.delivered), checks, failed: false});
  }
  for (const failure of receipt.failures) {
    if (symbols.has(failure.symbol)) rows.push({symbol: failure.symbol, failed: true, checks: []});
  }
  return {slot: receipt.scheduledTime, at: receipt.recordedAt, rows};
}

export async function snapshot(kv) {
  const latest = normalize(await kv.get("health:latest", "json"));
  if (!latest) throw new Error("Receipt unavailable");
  // Scheduled timestamps include jitter, so discover actual keys before bucketing.
  const latestBucket = Math.floor(latest.slot / PERIOD);
  const listing = await kv.list({prefix: "health:cron:", limit: 1000});
  const bySlot = new Map();
  for (const {name} of listing.keys) {
    const raw = Number(name.slice("health:cron:".length));
    const bucket = Math.floor(raw / PERIOD);
    if (!Number.isSafeInteger(raw) || bucket < latestBucket - 23 || bucket >= latestBucket) continue;
    if (!bySlot.has(bucket) || raw > bySlot.get(bucket).raw) bySlot.set(bucket, {raw, name});
  }
  const receipts = await Promise.all(Array.from({length:23}, async (_, i) => {
    const key = bySlot.get(latestBucket - 23 + i);
    const expected = latest.slot - (23 - i) * PERIOD;
    const raw = key?.raw ?? expected;
    const name = key?.name ?? "health:cron:" + raw;
    const value = normalize(await kv.get(name, "json"));
    return value?.slot === raw ? value : null;
  }));
  return {source: "kraken_spot", period: PERIOD, receipts: [...receipts, latest]};
}

export default {
  async fetch(request, env) {
    if(new URL(request.url).pathname === "/v1/live") return liveRoute(request, env);
    if (request.method !== "GET" || new URL(request.url).pathname !== "/v1/scans") return new Response(null, {status: 404});
    const token = request.headers.get("X-Scan-Reader");
    if (!env.READER_TOKEN || !token || token.length > 256) return new Response(null, {status: 403});
    const digest = value => crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
    const [actual, expected] = await Promise.all([digest(token), digest(env.READER_TOKEN)]);
    if (!crypto.subtle.timingSafeEqual(actual, expected)) return new Response(null, {status: 403});
    try {
      return Response.json(await snapshot(env.SIGNAL_STATE), {headers: {"Cache-Control":"private, no-store"}});
    } catch {
      return new Response("Scan receipts unavailable", {status: 503});
    }
  }
};
