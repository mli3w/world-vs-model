// World vs Model — fan-poll Worker (Cloudflare Workers + KV)
// =========================================================
// A tiny, cookieless vote counter for the static board. No PII, no tracking.
//   GET  /results        -> { counts: {team: n, ...}, total }
//   POST /vote {team}     -> records one allowlisted vote, returns the updated tally
//
// State is a single KV key "tallies" (a JSON object). CORS is locked to the site origin.
// A soft per-IP gate (12h) deters trivial ballot-stuffing; it is not airtight by design — this
// is a fan poll, not an election. If it ever needs exact concurrency, swap KV for a Durable Object.
//
// Research/education only — non-binding, not betting.

const ORIGIN = "https://mli3w.github.io";          // the GitHub Pages site allowed to call this

// The 48-team field (must match the names the site sends, i.e. worldcup_live.FIELD).
const ALLOW = new Set([
  "Mexico", "South Africa", "South Korea", "Czechia", "Canada", "Bosnia-Herzegovina",
  "Qatar", "Switzerland", "Brazil", "Morocco", "Haiti", "Scotland", "USA", "Paraguay",
  "Australia", "Türkiye", "Germany", "Curaçao", "Ivory Coast", "Ecuador",
  "Netherlands", "Japan", "Sweden", "Tunisia", "Belgium", "Egypt", "Iran", "New Zealand",
  "Spain", "Cape Verde", "Saudi Arabia", "Uruguay", "France", "Senegal", "Iraq", "Norway",
  "Argentina", "Algeria", "Austria", "Jordan", "Portugal", "DR Congo", "Uzbekistan",
  "Colombia", "England", "Croatia", "Ghana", "Panama",
]);

const VOTE_TTL = 12 * 60 * 60;                      // one vote per IP per 12 hours

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store",
  };
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { "Content-Type": "application/json", ...corsHeaders() },
  });
}

async function tally(env) {
  const counts = (await env.POLL.get("tallies", "json")) || {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  return { counts, total };
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders() });
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/results") {
      return json(await tally(env));
    }

    if (request.method === "POST" && url.pathname === "/vote") {
      let body;
      try { body = await request.json(); } catch (e) { return json({ error: "bad json" }, 400); }
      const team = body && body.team;
      if (!ALLOW.has(team)) return json({ error: "unknown team" }, 400);

      const ip = request.headers.get("CF-Connecting-IP") || "anon";
      const gate = "ip:" + ip;
      if (await env.POLL.get(gate)) {
        // already voted recently — return the current tally without double-counting
        return json({ ...(await tally(env)), counted: false });
      }
      const counts = (await env.POLL.get("tallies", "json")) || {};
      counts[team] = (counts[team] || 0) + 1;
      await env.POLL.put("tallies", JSON.stringify(counts));
      await env.POLL.put(gate, team, { expirationTtl: VOTE_TTL });
      const total = Object.values(counts).reduce((a, b) => a + b, 0);
      return json({ counts, total, counted: true, team });
    }

    if (url.pathname === "/") return json({ ok: true, service: "wvm-poll" });
    return json({ error: "not found" }, 404);
  },
};
