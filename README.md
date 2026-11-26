# breamfish

Fishing conditions, and in time a fish habitat map, for **Bream Bay and Urquharts Bay** near Whangārei, New Zealand.

Live site: <https://breamfishing.sonka.cloud.edu.au> (stage 0, live since 26 November 2026)

## What it does today

Stage 0 is a conditions site. For three zones (the harbour entrance, the inner bay and the outer bay with the Hen and Chickens) it shows wind, gusts, waves, rain and tide for the next seven days, and rates every hour as good, fair or poor for boat, kayak and shore fishing. The map shows the no-take marine reserve and boat ramps.

It does **not** yet say where the fish are. See [docs/roadmap.md](docs/roadmap.md) for what comes next and why the first fish layer will be a habitat index, not a catch prediction.

## How it works

```
push to main ──▶ CI: test, build frontend ──▶ `release` branch
                                                   │
                         Puppet agent on the server, every 30 minutes
                                                   ▼
server:  nginx ── /        static frontend (web/dist)
               └─ /data/*  JSON published by the pipeline
         breamfish-refresh.timer   hourly: fetch → rate → publish
```

- **`src/breamfish/`**: the pipeline. `breamfish refresh` fetches the sources, computes the comfort ratings and atomically writes `conditions.json` and `status.json`. If a source is down it reuses a cached copy and says so in `status.json`.
- **`web/`**: the frontend, in Vite, TypeScript, MapLibre GL and uPlot. It is fully static: no API, no database, no cookies. The basemap is a self-hosted OpenStreetMap extract, so the page loads nothing from other sites.
- **Deployment** is pull-based. CI publishes the `release` branch; the server's configuration lives in a separate Puppet control repo, which keeps the checkout at the head of that branch and puts back anything changed by hand. See [docs/runbook.md](docs/runbook.md).

## Run it locally

Needs [uv](https://docs.astral.sh/uv/) and Node 22 or newer.

```bash
uv sync
uv run breamfish refresh        # writes ./data/published/*.json from live sources
cd web
npm ci
npm run dev                     # serves the app and ./data/published at /data/
```

Checks, as CI runs them:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
cd web && npm run build
```

## The ratings

The comfort rating for each hour is the worst of three checks (wind, gusts, wave height) against limits for each fishing style, lowered one step for heavy rain, an offshore wind for kayaks, a strong onshore wind for shore fishing, or wind against an outgoing tide at the harbour entrance. The limits live in one place, [`src/breamfish/config.py`](src/breamfish/config.py), and the site's About panel displays them. They are sensible defaults, not safety advice.

Moon phase, solunar tables and barometric pressure are left out on purpose: published tests do not support them.

## Data and licences

The code is MIT licensed. The data is not ours: each source keeps its own terms, listed with attribution in [docs/data-sources.md](docs/data-sources.md). Open-Meteo's free tier is for non-commercial use.

No keys or secrets belong in this repo. Keys such as the LINZ Data Service key are kept encrypted in the Puppet control repo and reach the pipeline through an environment file on the server.

## Not for navigation

This is an experimental guide. Check the official marine forecast before you go, and the current fishing rules before you fish.
