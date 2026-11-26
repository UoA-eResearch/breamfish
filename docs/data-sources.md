# Data sources

What the site uses now, and what was checked for later stages. Every entry says how it was verified: **probed** means a live request for the Bream Bay box succeeded on 26 November 2026; **read** means it was read on a web page and not tested; **failed** means the request did not work.

Study box: latitude -36.12 to -35.78, longitude 174.38 to 174.80. This includes the Hen and Chickens.

## In use (stage 0)

| Source | Used for | Access | Licence and attribution |
|---|---|---|---|
| [Open-Meteo forecast](https://open-meteo.com/en/docs) | Wind, gusts, direction, rain, cloud, air temperature | `api.open-meteo.com/v1/forecast`, no key, several points per request | Data CC BY 4.0. Free tier is **non-commercial**, under 10,000 calls a day. The pipeline makes two calls an hour. |
| [Open-Meteo marine](https://open-meteo.com/en/docs/marine-weather-api) | Wave and swell height, period, direction; sea temperature | `marine-api.open-meteo.com/v1/marine`, no key | Same terms |
| [LINZ tide predictions](https://www.linz.govt.nz/products-services/tides-and-tidal-streams/tide-predictions) | High and low water at Marsden Point (standard port 079) | One CSV per year, 2023 to 2028: `static.charts.linz.govt.nz/tide-tables/maj-ports/csv/Marsden%20Point%20YYYY.csv` | CC BY 4.0, Toitū Te Whenua Land Information New Zealand |
| DOC marine reserves | No-take reserve polygons | ArcGIS feature service, fetched by `scripts/fetch_static_layers.py` and committed | CC BY 4.0, Department of Conservation. Indicative; the Order in Council is the legal boundary. |
| OpenStreetMap | Basemap and boat ramps | Protomaps daily build, extracted by `scripts/make_basemap.sh`; ramps from Overpass | ODbL, © OpenStreetMap contributors |

Things to know about these:

- **Forecast resolution.** The weather model grid is about 9 km and the wave model about 8 km. Requested points snap to the nearest grid cell, and wave cells sit several kilometres offshore. Nothing here resolves the harbour entrance or the shelter of Urquharts Bay.
- **Tide times are local.** The LINZ CSV header says "Local Std or Daylight Time". The pipeline converts to UTC; a slip here is a one-hour error for half the year.
- **The tide curve is interpolated** between predicted highs and lows with a cosine. Good to a few centimetres mid-tide, not a harmonic prediction.

## In use (stage 1, the seabed layers)

These are fetched once by `scripts/build_seabed.py` on a development machine, not by the server. The grids built from them are committed under `web/public/seabed/`. Method and datum handling are in [seabed.md](seabed.md); the numbers for the committed build are in [seabed-report.md](seabed-report.md). All were fetched on 26 November 2026.

| Source | Used for | Access | Licence and attribution |
|---|---|---|---|
| [LINZ coastal LiDAR](https://registry.opendata.aws/nz-coastal/), "Whangārei to Bream Bay" and "Mangawhai to Snells", flown March 2025 | Depth, slope and roughness near the coast: 27% of the sea in the box | Public bucket, no key: `nz-coastal.s3.ap-southeast-2.amazonaws.com/<region>/<survey>/dem_10m/2193/<tile>.tiff`. Tiles AX30, AX31, AY31 of the first survey and AY31, AY32 of the second. Cloud-optimised GeoTIFF in NZTM. | CC BY 4.0, Toitū Te Whenua Land Information New Zealand |
| [LINZ Shipping Lane 1 Multibeam 20m Depth Model (1999)](https://data.linz.govt.nz/layer/116628), surveys HS6 and HS15, 1999 to 2004 | Depth, slope and roughness across the middle of the bay: 39% of the sea | LINZ Data Service Exports API (`/services/api/v1.x/exports/`), layer 116628, cropped to the box, in its own UTM zone 60S. Needs a key that may create exports. | CC BY 4.0, Toitū Te Whenua Land Information New Zealand |
| [LINZ nautical chart data](https://data.linz.govt.nz/layer/50866), three scale bands | Depth elsewhere (34% of the sea), the land mask outside the LiDAR, survey dates, charted rock and seabed samples | LINZ Data Service WFS, `data.linz.govt.nz/services/wfs`, key sent in an `Authorization: key ...` header. Layer numbers below. | CC BY 4.0, Toitū Te Whenua Land Information New Zealand. Not to be used for navigation. |
| DOC Northland habitat map: Kerr, V.C. 2010, [Marine Habitat Map of Northland: Mangawhai to Ahipara](https://www.doc.govt.nz/documents/conservation/marine-and-coastal/northland-marine-habitat-map-report-1.pdf), version 1 | Bottom type where the chart says nothing | `seasketch.doc.govt.nz/arcgis/rest/services/National/NZMPASAG_Habitats_Northland_2009_201810/MapServer/0`, no key | **Licence not stated on the service.** Attributed to the Department of Conservation and the report's author. Worth confirming with DOC. |
| GEBCO 2020 | Background depth for water no chart covers. In this box that is no cells at all. | `api.opentopodata.org/v1/gebco2020`, no key, 100 points a call, one call a second | Public domain; GEBCO Compilation Group (2020) |

Chart layer numbers, by scale band (1:4k to 1:22k, 1:22k to 1:90k, 1:90k to 1:350k):

| Layer | Finest | Middle | Coarsest |
|---|---|---|---|
| Sounding points | 50858 | 50866 | 50506 |
| Depth contours | 50672 | 50554 | 50448 |
| Depth areas | 50671 | 50553 | 50447 |
| Land areas | 50691 | 50569 | 50461 |
| Quality of data (survey dates, zone of confidence) | 50707 | 50584 | 50476 |
| Seabed area polygons | 50734 | 50603 | 50496 |
| Seabed area points (samples) | 50733 | 50602 | 50495 |
| Underwater and awash rocks | 50755 | 50626 | 50513 |

Things to know about these:

- **Vertical datums differ and are reconciled in the build.** LiDAR is on NZVD2016; charts and the multibeam model are on chart datum; GEBCO is on mean sea level. Chart datum at Marsden Point is 1.746 m below NZVD2016. The derivation and its check are in [seabed.md](seabed.md).
- **The LiDAR goes deep.** It covers about 276 km² of sea in the box and reaches 40 m below chart datum, far beyond the shallow strip the first probe reported. It agrees with charted soundings to about half a metre at every depth that could be checked.
- **Only the 20 m multibeam model can be downloaded.** The index (layer 122710) also lists a 10 m surface for HS15, but the surfaces in that index are supplied on request by email to `hydro@linz.govt.nz`, not through the data service.
- **How old the depths are.** After the LiDAR and multibeam, about 26% of the sea rests on chart surveys since 1990 (nearly all a 2010 survey around the Hen and Chickens) and about 8% on surveys of 1955 to 1962. The earlier note that most of Bream Bay rests on 1962 surveys described the chart alone; the 2025 LiDAR and the multibeam model now cover most of that water.
- **The habitat map does not tell sand from mud over most of the bay.** About 77,000 of the 103,000 sea cells are "soft sediments" in it. The site shows that as its own class.
- **The `verdat` (vertical datum) attribute on chart features is empty.** The datum comes from LINZ's description of its charts, not from the data.
- **The LINZ key** is a 32-character API key made under your profile at data.linz.govt.nz. It needs query access for WFS and the `exports:write` scope for the multibeam export.

## Verified for later stages

### Seabed and depth

| Source | What it gives | Access | Status |
|---|---|---|---|
| LINZ coastal LiDAR, 1 m and 2 m grids | The same surveys as above at finer resolution | Same bucket, `dem_1m` and `dem_2m` | probed. Not needed at 100 m cells. CC BY 4.0. |
| LINZ multibeam surface, HS15 at 10 m | A finer surface for the inshore part of the shipping lane | By email request to LINZ, quoting the id from index layer 122710 | read. Not requested. |
| LINZ chart layers not used yet | Wrecks 50633, obstructions 50586/50587, cables 50546, restricted areas 50598 | LINZ Data Service WFS; needs the key | probed. CC BY 4.0. |
| LINZ survey index | Which survey each depth comes from | Layer 53388 | probed. The chart's own "quality of data" layers carry the same dates and were used instead. |
| NIWA 250 m bathymetry | National depth grid | NIWA download and image service | failed (HTTP 403 and 500). |

### Ocean

| Source | What it gives | Access | Status |
|---|---|---|---|
| MUR sea surface temperature | Daily, 0.01° grid, about two days behind | `coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41` | probed. Gaps at some cells in the harbour mouth. Its real detail is coarser than its grid, so use it as a seasonal signal, not for fronts. |
| Mangōpare fishing-gear sensors | Temperature at depth, from sensors on commercial gear | `erddap.emodnet-physics.eu/erddap/tabledap/moanaproject` | probed. 13,109 readings in the box, September 2022 to November 2026. CC BY 4.0. Position precision unchecked. Use for bottom temperature; do not plot positions, which would show individual fishers' marks. |
| NRC Hilltop | Ruakaka and Hatea river flow; Marsden Point water level since 1989 and harbour water temperature; a coastal water-quality buoy | `http://hilltop.nrc.govt.nz/data.hts` (plain HTTP only) | probed. Licence not stated. |
| VIIRS chlorophyll | About 4 km, ten days behind | NOAA CoastWatch ERDDAP `noaacwN20VIIRSchlaDaily` | probed. Too coarse to matter much here. |
| Copernicus Marine | Global physics forecast, 1/12° | `copernicusmarine` Python toolbox, free account | read. |
| Moana ocean hindcast | 5 km New Zealand hindcast, about 28 years | THREDDS at `thredds.moanaproject.org` | failed (timed out). Non-commercial licence. |

Nobody publishes tidal currents for the harbour entrance. That gap is what the cluster stage is for.

### Fish

| Source | What it gives | Access | Status |
|---|---|---|---|
| OBIS | About 6,200 fish records in the box. 3,608 are one snapper tagging cruise from late 1993 (about 55 positions, with depth and length); about 630 are research trawls with depth and catch weight, the latest from 2017; 1,001 are a 1990 to 1993 diver survey | `api.obis.org/v3/occurrence?geometry=<WKT>` | probed. Search snapper as *Pagrus auratus*; *Chrysophrys auratus* returns nothing. |
| iNaturalist | 913 fish observations, 802 research grade, mostly since 2020, median accuracy 54 m | `api.inaturalist.org/v1/observations` with a bounding box and `taxon_id=47178` | probed. Biased to what divers and shore walkers see. Mixed licences, many CC BY-NC. |
| Stephenson et al. 2023 fish atlas | Modelled distributions: reef fish on a 250 m grid (50 MB), demersal fish on 1 km (1.8 GB), with uncertainty | [Zenodo 7083642](https://zenodo.org/records/7083642) | probed (record). CC BY 4.0. Whether its snapper layer is useful at this scale is unchecked. |
| Fisheries New Zealand catch data | Commercial catch by statistical area | Areas 003 (about 14,300 km²) and 005 (about 2,660 km²) cover the box | probed (boundaries). Far too coarse to place fish within the bay. |
| Recreational surveys | National Panel Survey, boat-ramp interviews and cameras | PDF reports only | read. No data at bay scale. |
| Global Fishing Watch | AIS fishing effort at about 0.01° | API needs a free token; CC BY-NC | read. Inshore vessels here mostly carry no AIS, so expect little. |

**There is no public fine-scale record of where fish are caught in this bay.** That is why the first fish layer is a habitat index validated against the sparse points above.

### Rules

| Item | Source | Status |
|---|---|---|
| Whangārei Harbour Marine Reserve (Motukaroro 26 ha, Waikaraka 210.5 ha), no-take | DOC feature service, in use | probed |
| Shellfish closure on Mair and Marsden Banks, 29 June 2026 to 28 June 2028 | Gazette notice 2026-sl3443 | read. Closure polygons were not obtainable: the MPI map server timed out. |
| Bag and size limits | MPI web pages and the NZ Fishing Rules app | read. No machine-readable feed exists, so the site links to the rules and does not restate them. |

### Evidence on popular beliefs

- Solunar tables failed a direct test of predicting catch ([Quigley 2023](https://link.springer.com/article/10.1007/s42452-023-05379-8)).
- A New Zealand snapper diary study found only weak lunar effects (Marine Ecology Progress Series 151:219), and moon phase is hard to separate from tide strength.
- No published support was found for barometric pressure.
- The often-quoted 18 °C for snapper comes from year-class strength, not a spawning trigger; first spawning was observed at 14.8 to 15.6 °C. See Parsons et al. 2014, [doi:10.1080/00288330.2014.892013](https://doi.org/10.1080/00288330.2014.892013).
