# Working on breamfish

A public repo. A fishing-conditions site for Bream Bay and Urquharts Bay, growing in stages into a habitat-suitability map. Read [docs/roadmap.md](docs/roadmap.md) for the stages and [docs/data-sources.md](docs/data-sources.md) for which sources are verified.

## Commands

```bash
uv sync                                   # Python env (3.13+; the server runs 3.14)
uv run breamfish refresh                  # live run, writes ./data/published/
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
cd web && npm ci && npm run dev           # app at :5173, serves ../data/published at /data/
cd web && npm run build                   # type-check + production build
python3 scripts/fetch_static_layers.py    # refresh reserves + ramps GeoJSON (committed)
scripts/make_basemap.sh                   # rebuild the self-hosted basemap (committed)
uv run python scripts/build_seabed.py     # rebuild the seabed grids (committed; needs LINZ_API_KEY once)
```

## Layout

- `src/breamfish/`: pipeline. `config.py` holds zones and every threshold; `publish.py` defines the JSON the frontend reads.
- `web/src/data.ts`: the TypeScript mirror of that JSON. Change both sides together.
- `web/public/`: committed static assets (tiles, fonts, sprites, layers, the seabed grids).
- `scripts/seabed/` and `scripts/build_seabed.py`: the hand-run seabed build, described in [docs/seabed.md](docs/seabed.md). `web/src/seabed.ts` reads what `scripts/seabed/publish.py` writes; change both sides together.
- `.github/workflows/ci.yml`: tests, builds, and publishes the `release` branch that the server runs.

## Rules that are easy to break

- **No secrets here, ever.** Keys live in eyaml in the private Puppet control repo and arrive as environment variables (`/etc/breamfish/env`). Read them with `os.environ.get`, and make the code work without them.
- **The browser calls nobody but this site.** All sources are fetched server-side and republished. No CDN scripts, fonts or tiles. The nginx Content-Security-Policy enforces this, so a third-party URL will simply break.
- **No runtime dependence on an LLM or any paid API.** Anything of that kind is an optional batch step that is skipped cleanly when no key is present.
- **The formula lives in Python only.** The frontend displays what the pipeline computed; it never recomputes a rating or score.
- **Publish atomically and never replace good data with nothing.** Keep `status.json` honest about stale or failed sources.
- **Call it what it is.** Ratings are "comfort" for conditions; the future fish layer is a "habitat and conditions index", never a catch probability. No solunar tables, moon phase or barometric pressure as inputs.
- **Times:** UTC in data, `Pacific/Auckland` for display. LINZ tide tables are in local time.
- Keep the Python small and plain (stdlib, httpx, astral). No framework. New dependencies need wheels for Python 3.14, because the server installs with `pip --require-hashes` and has no compilers.
- **Geospatial libraries stay in the `dev` group.** numpy, rasterio, scipy and contourpy are for `scripts/` and the tests only. Nothing under `src/breamfish/` may import them: the server installs the runtime dependencies alone.
- **Depths are metres below chart datum at Marsden Point.** A source on another datum is converted in `scripts/seabed/depth.py`, with the figure's origin beside it.

## Deploying

Merging to `main` is the deploy: CI publishes `release`, and the server's Puppet agent picks it up within 30 minutes. Server configuration (nginx, certificate, systemd units, the checkout itself) is in the Puppet control repo under `site::profile::breamfish` and `site::profile::breamfish_web`; change it there, not on the server. See [docs/runbook.md](docs/runbook.md).
