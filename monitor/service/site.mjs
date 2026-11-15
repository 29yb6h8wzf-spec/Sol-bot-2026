export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (request.method !== "GET") return new Response(null, {status:405});
    if (path === "/api/scans") {
      if (!env.READER_TOKEN) return new Response(null, {status:503});
      try {
        const response = await fetch("https://signalpilot-scan-desk-feed.29yb6h8wzf.workers.dev/v1/scans", {
          headers: {Authorization: "Bearer " + env.READER_TOKEN}, redirect: "error", signal: AbortSignal.timeout(12000)
        });
        if (!response.ok) throw new Error("Feed unavailable");
        return new Response(response.body, {headers: {"Content-Type":"application/json","Cache-Control":"private, no-store"}});
      } catch { return new Response(null, {status:503}); }
    }
    if (path !== "/") return new Response(null, {status:404});
    return new Response(PAGE, {headers: {"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-cache","X-Content-Type-Options":"nosniff"}});
  }
};
