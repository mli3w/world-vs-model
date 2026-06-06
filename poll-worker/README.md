# wvm-poll — the fan-poll backend (Cloudflare Worker + KV)

A ~70-line Cloudflare Worker that stores the "Who wins the World Cup 2026?" votes for the static
board. Free tier, cookieless, no PII. The board talks to it from the browser:

- `GET  /results` → `{ "counts": { "Spain": 12, ... }, "total": 37 }`
- `POST /vote` with body `{ "team": "Spain" }` → records one allowlisted vote, returns the new tally

State is a single KV key (`tallies`). CORS is locked to the site origin; a soft per-IP gate (12h)
deters casual ballot-stuffing. This is a fan poll, not an election — exact concurrency isn't a goal.

## One-time deploy (about 10 minutes)

You need a free [Cloudflare](https://dash.cloudflare.com/sign-up) account. Then, from this folder:

```bash
npm install -g wrangler          # the Cloudflare CLI (or: npx wrangler ...)
wrangler login                   # opens a browser to authorize

# 1) create the KV namespace — copy the "id" it prints
wrangler kv namespace create POLL

# 2) paste that id into wrangler.toml (replace REPLACE_WITH_YOUR_KV_NAMESPACE_ID)

# 3) (optional) if your site is on a different domain, edit ORIGIN at the top of worker.js

# 4) ship it
wrangler deploy
```

`wrangler deploy` prints a URL like `https://wvm-poll.<your-subdomain>.workers.dev`. That is your
endpoint.

## Wire it into the board

Set the endpoint so the board renders the poll bubble. Either:

- export an env var before building: `WVM_POLL_ENDPOINT="https://wvm-poll.<sub>.workers.dev"`, **or**
- set `POLL_ENDPOINT` directly in `src/worldcup_board.py`.

For the live site (the GitHub Actions hourly rebuild), add the URL as a repo **Variable**
(Settings → Secrets and variables → Actions → Variables → `WVM_POLL_ENDPOINT`) and the workflow
passes it through. Until the endpoint is set, the bubble simply doesn't render — nothing half-built
ships publicly.

## Quick test

```bash
curl https://wvm-poll.<sub>.workers.dev/results
curl -X POST https://wvm-poll.<sub>.workers.dev/vote -H 'content-type: application/json' -d '{"team":"Spain"}'
```

The vote keys are the exact team names in `src/worldcup_live.py` (`FIELD`) — keep the `ALLOW` set in
`worker.js` in sync if the field ever changes.
