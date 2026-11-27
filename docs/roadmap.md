# Roadmap

Each stage ends with something live on the site.

| Stage | What goes live | Main data |
|---|---|---|
| **0 Skeleton** (live since 26 November 2026) | HTTPS site, map, no-take reserve, boat ramps, seven-day conditions with a comfort rating for boat, kayak and shore | Open-Meteo, LINZ tides, DOC reserves, OpenStreetMap |
| **1 Seabed** (live since 26 November 2026) | Merged depth surface with a depth-quality overlay, contours, slope and roughness, reef, sand and mud; tap a spot for depth and bottom type | LINZ LiDAR, multibeam and chart layers, DOC habitat map |
| **2 Snapper habitat** (built 26 November 2026) | Seasonal snapper habitat index in five classes, reach for kayak and shore fishing, a methods page, first numbers against real records; seabed layers drawn at 20 m when zoomed in | Stage 1 grids, published studies, OBIS and iNaturalist points |
| **2b Wind on the map** (built 27 November 2026) | The forecast wind drawn moving over the map for the hour chosen in the panel; still arrows where the device asks for less motion | Open-Meteo, a lattice of 48 model cells |
| **2c Seabed relief** (built 28 November 2026) | Shaded relief where the depth was measured, so reefs, channels and banks show as shapes; a rough-ground layer, shown on the map and in a tap, to find reef the habitat map misses. Flat shading only, no tilted 3D view | LINZ LiDAR at 2 m, the 20 m multibeam model |
| 3 Dynamic index | Hourly seven-day frames, time slider, a "why this score" panel, best-window summary, offline caching | Satellite sea temperature, tide stage and range, Ruakaka river flow |
| 4 Evidence loop | A "how good is this?" page, bottom temperature from fishing-gear sensors, a templated daily briefing, a rules watcher, an optional catch log, weak labels from published fishing reports | Mangōpare sensors, fishing reports |
| 5 Cluster | Modelled tidal currents and nearshore waves replace the proxies; a daily wind forecast at about 1 km replaces the lattice | One-off and daily jobs on a Slurm cluster |
| 6 More species | Kingfish, kahawai, trevally, gurnard, john dory | As above |

## Why a habitat index and not a catch prediction

A catch predictor needs records of where and when fish were caught. For this bay those do not exist in public: commercial catch is published only for areas thousands of square kilometres across, and recreational catch only as regional tables. See [data-sources.md](data-sources.md).

So the fish layer will be a **habitat and conditions index**:

- built from published response curves (depth by season, bottom type, distance to reef edge, water temperature, tide stage), one file per species with a citation for each curve. Stage 2 has the first three; see [habitat.md](habitat.md);
- combined as a weighted geometric mean, so every cell can show how much each factor contributed;
- shown in five classes, not as a percentage;
- checked against the point records that do exist, with the result published on the site;
- masked inside the no-take reserve.

Wind and sea state do not enter the fish index. They grey a cell out for a fishing style when it is not comfortable to be there.

A catch log comes later, to start building the local dataset that would let the index be tested and eventually fitted.

## Left over from stage 2

- **The 2023 fish atlas** (Stephenson et al.) has not been compared with the index. Its demersal fish layers are a 1.8 GB download.
- **Tows that caught no snapper.** The research trawl records would allow a presence-and-absence test; only the tows that caught snapper are used so far.
- **Accessible shoreline.** Shore reach is every stretch of mainland shore. Whether it can be reached on foot (a road, a track, a beach) is not checked.

## Left over from stage 2c

- **Rough ground is shown but not used.** It does not enter bottom type, distance to reef or the habitat index. The report says what the numbers would support: a fourth source of bottom type below the chart, its samples and the habitat map, as a class of its own, with a line that rises with depth ([seabed.md](seabed.md)). Before that, build the habitat index with and without it and compare the two against the snapper records.
- **It tells rock from sand no better than the roughness the 100 m grid already had.** A measure that also used the shape of the ground (the relief shows reefs clearly to the eye) might do better than either. Not tried.
- **The multibeam's relief is from 20 m cells.** A 10 m surface for part of it exists by email request to LINZ ([data-sources.md](data-sources.md)).

## Design decisions already made

- **Grid:** NZTM (EPSG:2193) at 100 m, about 380 by 380 cells. Slope and roughness are computed at 10 m where LiDAR or multibeam exists, then summarised to the cell. A second grid at 20 m is for drawing only; nothing is computed from it.
- **Species files are TOML**, not YAML: Python reads TOML from its standard library, and the server installs nothing extra.
- **Classes are cut within each season.** The curves give the shape of a season, not how one season compares with another, so "highest" means the best fifth of the bay for that time of year.
- **Depth merge:** LiDAR where valid, multibeam across the middle of the bay, chart soundings elsewhere, a global grid as background, with a `depth_source` layer so the site can show how good the depth is at each spot. Depths are metres below chart datum at Marsden Point, which is 1.746 m below the LiDAR's datum, NZVD2016. Built in stage 1; see [seabed.md](seabed.md).
- **Bottom type** keeps "soft sediment, sand or mud not told apart" as a class of its own, because that is all the habitat map says for most of the open bay. Stage 2 response curves must treat it as such and not as sand.
- **Delivery:** static files only. Compressed byte grids for static factors, then the index and its factor contributions per hour, painted in the browser a map tile at a time. No tile server, no API. The formula lives in Python.
- **Shore fishing** is scored per stretch of shoreline, not per grid cell: a point every 100 m, rated by the water a cast can reach.
- **Left out on purpose:** solunar tables, moon phase (spring and neap range is kept, through the tide), barometric pressure. Also collecting photographs from social media or through an image search: the platforms strip positions from the copies they show, their terms forbid it, and Google's search API closes on 1 January 2027 ([data-sources.md](data-sources.md)).
- **Relief is drawn only where the depth was measured**, by LiDAR or multibeam, and never on charted water: between soundings the surface is a guess, and shading it would draw reefs nobody measured. It is flat shading, shipped as map tiles made once from each survey's own grid; the browser computes nothing.
- **Wind is drawn, not scored.** The streaks on the map show the forecast as published. Strength is carried by speed, length and weight of line, not colour, because every colour on the map already means something. Nothing about the wind enters the fish index.

## Where a cluster helps, and where it does not

It does not help the website or the hourly pipeline, which take seconds on one small server. It does not help the fish index either: that is short of records, not of computing. It helps with the physics, in two one-off jobs whose results are small files the server can use indefinitely, and one daily job:

1. **A 2D tidal model of the harbour and bay** (SCHISM or Delft3D-FM, run with MPI in restartable chunks), validated against the Marsden Point gauge and reduced to harmonic constituents for each cell. This fills the one real data gap: nobody publishes currents at the harbour entrance. The currents can be drawn by the same code that draws the wind (`web/src/flow.ts`).
2. **A nearshore wave lookup table** (SWAN, as a job array over offshore height, period and direction), because the public wave forecast stops several kilometres offshore.
3. **A daily wind forecast at about 1 km** (decided 27 November 2026). The public forecast works in squares about 8 by 10 km, four or five across the bay, and cannot show the shelter under Bream Head or Manaia. A regional weather model nested down to the bay could. It writes a `wind.json` of the shape the site already reads, so nothing on the site changes. The Open-Meteo lattice stays as the fallback: the site must never depend on the cluster having run. It has to be checked against wind measured at Marsden Point before it is shown.

The first of these is built, on trial (28 November 2026). The cluster runs the WRF weather model over three nested areas, down to 1 km around the bay, for 72 hours ahead, once a day, from the public GFS forecast. One 32-core node takes about 70 minutes. It publishes the 10 m wind to a public object-store address; the web server fetches it there, so the two never need a network path to each other. The pipeline reads it only when the server has been given the address (`BREAMFISH_FINE_WIND_URL`).

**It is shown to everyone, labelled as on trial** (decided 28 November 2026: the site is in development and nobody relies on it yet, so new things go out and are judged in use). The note under the map's wind key says it has not yet been checked against measured wind; `?fine=0` hides it in a browser. Checking it against measured wind is set up on the cluster, and the first results are in [wind-check.md](wind-check.md). Two things were known about it before that. At 1 km a ridge as narrow as Bream Head is still flattened: the model's terrain puts it at 116 m, and it is about 470 m. And the first run agreed with the public forecast to within about 1 knot and 25 degrees at the three zone points, which says it is not wrong and not yet that it is better.

## Where a language model might help, and where it must not

No part of the running site depends on one. Possible optional batch uses, run only when an API key is present:

- turning published fishing reports into structured facts (date, places named, species, size, good or slow), storing the facts and a link, never the prose, as records to test the habitat index against. Chosen on 27 November 2026 as the next source of records. An open-weights model run on a GPU of our own is neither a paid API nor a runtime dependence: since 28 November 2026 one runs in batch jobs on the cluster's L4 (Qwen3-VL-8B, Apache 2.0). Places named in a report are turned into positions with the New Zealand Gazetteer.

Only sources whose terms and `robots.txt` allow it, approved one by one; not social media, image search or discussion forums (whose terms forbid automated collection, and which strip a photo's position anyway). The draft list is `docs/report-sources-draft.md` until it is approved.

The same pages carry photographs, and a photograph's file sometimes records where and when it was taken. Reading that needs no model; the model can check the species. Before building anything, fetch a few hundred originals from approved sources and count how many carry a position in the bay. Positions are kept as recorded, not coarsened (decided 28 November 2026): the index works on 100 m squares, and testing it needs that precision. A position is where the picture was taken, though, and only positions on the water are kept. One on land is the ramp, the car park or the kitchen bench, says nothing about where the fish was, and may be somebody's home. Store the date, the position and the link, never the image. How they are shown on the map (points, or counts per square) is to be decided when there are some.

It must never compute or adjust scores, state regulations, or give go or no-go advice. The daily briefing is templated text from the forecast numbers, and the rules watcher is a scheduled job that opens an issue when an official page changes.
