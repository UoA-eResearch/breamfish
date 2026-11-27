# Working on breamfish

A public repo. A fishing-conditions site for Bream Bay and Urquharts Bay with a seabed map, shaded relief and a snapper habitat index, growing in stages. Read [docs/roadmap.md](docs/roadmap.md) for the stages and [docs/data-sources.md](docs/data-sources.md) for which sources are verified.

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
uv run python scripts/build_relief.py     # rebuild the relief tiles and rough ground (committed; after build_seabed.py; no key)
uv run python scripts/build_habitat.py    # rebuild the habitat index (committed; run after build_seabed.py or a species file change)
python3 scripts/fetch_habitat_points.py   # refresh the snapper records the index is tested against (committed)
```

## Layout

- `src/breamfish/`: pipeline. `config.py` holds zones and every threshold; `publish.py` defines the JSON the frontend reads.
- `web/src/data.ts`: the TypeScript mirror of that JSON. Change both sides together.
- `wind_fine.json` (`publish.build_fine_wind`, `sources/cluster_wind.py`): our own 1 km wind forecast, run on a cluster and fetched from the address in `BREAMFISH_FINE_WIND_URL`. Optional and on trial: with no address the source does not exist, and the site draws it only with `?fine=1`. The same `VectorField` shape, so `flow.ts` draws either.
- `wind.json` (`publish.build_wind`, `VectorField` in `data.ts`): the forecast wind at a lattice of model cells, set out in `config.WIND_LATTICE`. `web/src/flow.ts` draws it moving over the map and can draw any field published in that shape.
- `web/public/`: committed static assets (tiles, fonts, sprites, layers, the seabed grids).
- `scripts/seabed/` and `scripts/build_seabed.py`: the hand-run seabed build, described in [docs/seabed.md](docs/seabed.md). `web/src/seabed.ts` reads what `scripts/seabed/publish.py` writes; change both sides together.
- `scripts/build_relief.py`, with `scripts/seabed/relief.py` (shading, rough ground) and `tiles.py` (map tiles in PMTiles archives): the second hand-run build. It writes `web/public/tiles/relief_*.pmtiles` and `web/public/seabed/fine_roughness.bin.gz`, and owns two entries of the seabed manifest (`relief`, `layers.fine_roughness`) and the last section of `docs/seabed-report.md`. `build_seabed.py` carries those over when it rewrites the rest. `web/src/map.ts` adds the archives as raster sources through the `pmtiles` protocol.
- `src/breamfish/habitat.py` and `src/breamfish/species/snapper.toml`: the habitat index and everything it is built from, described in [docs/habitat.md](docs/habitat.md). `scripts/build_habitat.py` writes `web/public/habitat/`; `web/src/habitat.ts` and `web/src/methods.ts` read it. `grids.py` and `nztm.py` read grids and project points without numpy.
- `web/src/paint.ts`: paints any grid onto the map a tile at a time. `web/methods.html` is the second page of the site.
- `.github/workflows/ci.yml`: tests, builds, and publishes the `release` branch that the server runs.

## Rules that are easy to break

- **No secrets here, ever.** Keys live in eyaml in the private Puppet control repo and arrive as environment variables (`/etc/breamfish/env`). Read them with `os.environ.get`, and make the code work without them.
- **The browser calls nobody but this site.** All sources are fetched server-side and republished. No CDN scripts, fonts or tiles. The nginx Content-Security-Policy enforces this, so a third-party URL will simply break.
- **No runtime dependence on an LLM or any paid API.** Anything of that kind is an optional batch step that is skipped cleanly when no key is present.
- **The formula lives in Python only.** The frontend displays what the pipeline computed; it never recomputes a rating or score.
- **The site never depends on the cluster.** What the cluster publishes is read as something that may be late, missing or wrong: checked value by value, dropped when old, and always with the public forecast to fall back on. An optional source is marked `optional` in `status.json` and does not count towards `ok`.
- **Publish atomically and never replace good data with nothing.** Keep `status.json` honest about stale or failed sources.
- **Call it what it is.** Ratings are "comfort" for conditions; the fish layer is a "habitat index", never a catch probability or a forecast. No solunar tables, moon phase or barometric pressure as inputs.
- **Every number in a species file says where it comes from.** A curve has a `basis` (what is published) and a `judgement` (what was decided here); evidence cites a reference that says how much of it was read. Do not add a figure from memory: read the source, or mark it as judgement.
- **Rebuild what depends on what you changed.** The habitat grids are built from the seabed grids and the species file; `tests/test_habitat_build.py` fails until `scripts/build_habitat.py` has been run and its output committed. The relief and rough ground are built from the seabed grids too: after `build_seabed.py`, run `build_relief.py`.
- **Shade only what was measured.** The relief comes from the LiDAR and the multibeam, each on its own grid. Never shade the charted surface or the drawing grid: between soundings the shape is a guess.
- **Rough ground feeds nothing.** `fine_roughness` is published and shown. It is not an input to bottom type, distance to reef or the habitat index until that has been tested ([docs/roadmap.md](docs/roadmap.md)).
- **The relief archives are 16 MB of committed binary.** Rebuilding them adds that to the history each time the bytes change. Tell the user before committing a build that takes them past 20 MB.
- **The 20 m drawing grid is for drawing.** Slope, roughness, distances and the habitat index come from the 100 m grid only.
- **Times:** UTC in data, `Pacific/Auckland` for display. LINZ tide tables are in local time.
- Keep the Python small and plain (stdlib, httpx, astral). No framework. New dependencies need wheels for Python 3.14, because the server installs with `pip --require-hashes` and has no compilers.
- **Geospatial libraries stay in the `dev` group.** numpy, rasterio, scipy and contourpy are for `scripts/` and the tests only. Nothing under `src/breamfish/` may import them: the server installs the runtime dependencies alone.
- **Depths are metres below chart datum at Marsden Point.** A source on another datum is converted in `scripts/seabed/depth.py`, with the figure's origin beside it.

## Deploying

Merging to `main` is the deploy: CI publishes `release`, and the server's Puppet agent picks it up within 30 minutes. Server configuration (nginx, certificate, systemd units, the checkout itself) is in the Puppet control repo under `site::profile::breamfish` and `site::profile::breamfish_web`; change it there, not on the server. See [docs/runbook.md](docs/runbook.md).
