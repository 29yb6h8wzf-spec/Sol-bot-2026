/** Authenticated owner-only Binance Futures research notifications.
 * No trading, no order endpoints, no acceptance of market prices.
 * Requires a separately provisioned shared secret in both environments.
 */
const SYMBOLS = new Set(["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]);
const ROUTE = "/internal/binance-research";

function hex(bytes) {
  return [...bytes].map(x => x.toString(16).padStart(2, "0")).join("");
}

export function validateBinanceResearchEnvelope(body, nowSeconds) {
  if (!body || typeof body !== "object" || Array.isArray(body) ||
      Object.keys(body).sort().join(",") !==
      "direction,execution_authorized,orders_sent,score,signal_id,source,symbol,timestamp,type") {
    throw new Error("invalid_envelope");
  }
  if (body.type !== "SIGNALPILOT_BINANCE_RESEARCH_V1" ||
      body.source !== "verified_85_score_engine" ||
      body.execution_authorized !== false || body.orders_sent !== false ||
      !SYMBOLS.has(body.symbol) ||
      !["long", "short"].includes(body.direction) ||
      !Number.isInteger(body.score) || body.score < 85 || body.score > 95 ||
      !Number.isInteger(body.timestamp) ||
      nowSeconds < body.timestamp || nowSeconds - body.timestamp > 120 ||
      typeof body.signal_id !== "string" ||
      !/^r-[0-9a-f]{24}$/.test(body.signal_id)) {
    throw new Error("invalid_or_stale_research");
  }
  return body;
}

export async function verifyBinanceResearchSignature(secret, timestamp, raw, signature, nowSeconds) {
  if (typeof secret !== "string" || secret.length < 32 ||
      !/^\d{10}$/.test(timestamp || "") ||
      Math.abs(nowSeconds - Number(timestamp)) > 90 ||
      !/^[0-9a-f]{64}$/.test(signature || "")) return false;
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" },
    false, ["verify"]);
  const bytes = new Uint8Array(signature.match(/.{2}/g).map(x => parseInt(x, 16)));
  return crypto.subtle.verify("HMAC", key, bytes, encoder.encode(timestamp + "." + raw));
}

export async function handleBinanceResearch(request, env, { sendOwner } = {}) {
  if (new URL(request.url).pathname !== ROUTE) return new Response("Not found", { status: 404 });
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
  if (!env.BINANCE_RESEARCH_INGEST_SECRET || !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    return new Response("Research bridge disabled", { status: 503 });
  }
  const raw = await request.text();
  if (raw.length > 2048) return new Response("Payload too large", { status: 413 });
  const timestamp = request.headers.get("x-signalpilot-timestamp");
  const signature = request.headers.get("x-signalpilot-signature");
  const now = Math.floor(Date.now() / 1000);
  if (!await verifyBinanceResearchSignature(
    env.BINANCE_RESEARCH_INGEST_SECRET, timestamp, raw, signature, now)) {
    return new Response("Unauthorized", { status: 401 });
  }
  let body, testOnly = false;
  try {
    const parsed = JSON.parse(raw);
    if (parsed.type === "SIGNALPILOT_BINANCE_BRIDGE_TEST_V1") {
      if (Object.keys(parsed).sort().join(",") !==
          "execution_authorized,nonce,orders_sent,timestamp,type" ||
          parsed.execution_authorized !== false || parsed.orders_sent !== false ||
          !Number.isInteger(parsed.timestamp) || Math.abs(now - parsed.timestamp) > 90 ||
          typeof parsed.nonce !== "string" || !/^test-[0-9a-f]{24}$/.test(parsed.nonce)) {
        throw new Error("invalid_test");
      }
      body = parsed;
      testOnly = true;
    } else {
      body = validateBinanceResearchEnvelope(parsed, now);
    }
  } catch {
    return new Response("Invalid or expired research", { status: 422 });
  }
  // Stateless Cloudflare relay: the free KV daily write quota can be exhausted.
  // AWS alone serializes publication and durably claims each research signal
  // BEFORE sending HTTPS. No retries after ambiguous delivery. HMAC + timestamp
  // protect this endpoint; the relay itself does not guarantee replay prevention.
  // Never send from a second publisher or log signed requests.
  const message = testOnly ? [
    "🧪 SIGNALPILOT — בדיקת חיבור",
    "AWS → Cloudflare → Telegram",
    "זו הודעת בדיקה בלבד, לא איתות מסחר.",
    "🚫 לא נפתחה עסקה ולא הופעל מסחר אוטומטי."
  ].join("\n") : [
    "🔔 SIGNALPILOT | Binance Futures — מחקר",
    body.symbol + " | " + body.direction.toUpperCase() +
      " | דירוג תנאים " + body.score + "/100",
    "נר מאומת: " + new Date(body.timestamp * 1000).toISOString(),
    "מקור: Binance Futures | סריקת AWS",
    "⚠️ אין כאן מחיר כניסה, סטופ או יעד. לא הוראת מסחר.",
    "🚫 לא בוצעה עסקה. ציון אינו הסתברות הצלחה."
  ].join("\n");
  try {
    if (typeof sendOwner !== "function") throw new Error("missing_delivery_handler");
    await sendOwner(env, String(env.TELEGRAM_CHAT_ID), message);
    return Response.json({ status: "delivered_owner_only", research_only: true, test_only: testOnly });
  } catch {
    return Response.json({ status: "delivery_unconfirmed", research_only: true }, { status: 502 });
  }
}
