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

## Verified for later stages

### Seabed and depth

| Source | What it gives | Access | Status |
|---|---|---|---|
| LINZ coastal LiDAR, "Whangārei to Bream Bay 2025" | Land and shallow seabed heights on 1, 2 and 10 m grids, captured March 2025 | Public bucket, no key: `nz-coastal.s3.ap-southeast-2.amazonaws.com/northland/whangarei-to-bream-bay_2025/dem_{1m,2m,10m}/2193/collection.json`, cloud-optimised GeoTIFF in NZTM | probed. Only the shallow strip has data. Values to -40 m were seen, deeper than this kind of survey usually reaches, so treat the deep end as suspect. Vertical datum not yet confirmed. CC BY 4.0. |
| LINZ multibeam surfaces | HS15 "Shipping Lane 1, inshore" on a 10 m grid (2000 to 2014) and HS6 offshore on 20 m | LINZ Data Service, index layer 122710; needs the LINZ key | probed (index). Vertical datum is lowest astronomical tide. |
| LINZ chart layers | Depth areas 50553, soundings 50866, contours 50554, seabed type polygons 50603 and points 50602, wrecks 50633, obstructions 50586/50587, rocks 50626, cables 50546, restricted areas 50598 (finer scale band: 50671, 50858, 50672) | `data.linz.govt.nz/services;key=KEY/wfs`; needs the LINZ key | probed. 47 rock polygons and 56 seabed samples (sand, shell, mud, rock) in the box. CC BY 4.0. |
| LINZ survey index | Which survey each depth comes from | Layer 53388 | probed. Most of Bream Bay rests on Navy surveys from 1962; the Hen and Chickens on a 2010 echo-sounder survey at 125 m line spacing. |
| DOC Northland habitat map (Kerr 2009) | Reef, sand and fine-sediment polygons with depth class | `seasketch.doc.govt.nz/arcgis/rest/services/National/NZMPASAG_Habitats_Northland_2009_201810/MapServer/0` | probed. Coarse mapping scale; licence not stated. |
| GEBCO | Global depth, about 450 m | via `api.opentopodata.org/v1/gebco2020` | probed. Fallback only. |
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
