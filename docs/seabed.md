# The seabed layer

Stage 1 of the [roadmap](roadmap.md). The site shows depth, how far that depth can be trusted, bottom type and depth contours, and a tap on the water reads them for one spot. The snapper habitat index ([habitat.md](habitat.md)) is built on these grids.

There are two sets of grids. The **100 m grid** is the one every computed number comes from: slope, roughness, the distances, and the habitat index. The **20 m drawing grid** is the same sources laid out five times finer, for the map to paint when zoomed in and for a tap to read. Nothing is computed from the drawing grid.

Everything here is static. `scripts/build_seabed.py` is run by hand on a development machine, and its outputs are committed under `web/public/seabed/`. The server never runs it and never installs the libraries it needs.

## Rebuilding

```bash
export LINZ_API_KEY=...                  # LINZ Data Service key; never commit it
uv run python scripts/build_seabed.py
```

Create the key at [data.linz.govt.nz](https://data.linz.govt.nz/) (your profile, API keys). It is a 32-character string, not your password. It needs query access for the chart layers (WFS) and permission to create exports (the API calls the scope `exports:write`) for the multibeam grid. The script sends it as a request header, so it never appears in a URL or an error message.

The script downloads each source once into `data/seabed/raw/` (ignored by git). Later runs read that cache and need neither the network nor the key; delete a cached file to fetch it again. It writes:

| File | What |
|---|---|
| `web/public/seabed/manifest.json` | Grid, value scaling, class legends, source and licence for each layer |
| `web/public/seabed/*.bin.gz` | One 100 m grid per layer: depth, depth source, slope, roughness, bottom, bottom source, distance to reef, distance to the mainland shore |
| `web/public/seabed/drawing_*.bin.gz` | The 20 m drawing grid: depth, depth source, bottom, bottom source |
| `web/public/seabed/contours.geojson` | Depth contours, drawn from the 20 m depth |
| `docs/seabed-report.md` | Cell counts and the checks against charted soundings for this build |

Review the diff, read the report, and commit all of them together. The same inputs give byte-identical grids, so a diff means the data changed.

Rebuild the habitat index afterwards (`uv run python scripts/build_habitat.py`): it reads these grids, and a test fails if it is out of date.

The code is in `scripts/seabed/`: `grid.py` (the grid), `depth.py` (datums, merge, slope, roughness), `bottom.py` (bottom type), `distance.py` (distance to reef and to the mainland shore), `drawing.py` (the 20 m drawing grid), `sources.py` (downloads), `publish.py` (file formats), `report.py` (the checks). `tests/test_seabed_*.py` cover them without touching the network; `tests/test_seabed_build.py` runs the whole build on a made-up scene.

## The grid

NZTM (EPSG:2193), 100 m cells, 386 columns by 384 rows, north-west corner at 1 724 100 E, 6 039 600 N. It is the smallest block of whole cells that contains the study box (latitude -36.12 to -35.78, longitude 174.38 to 174.80). Rows run north to south.

The 10 m LiDAR and 20 m multibeam rasters are laid on grids that nest exactly inside this one, so a cell is always a whole block of fine cells.

## Vertical datum

All depths are **metres below chart datum at Marsden Point**, positive down. That is the zero of the LINZ charts and of the tide predictions the site shows, so depth plus tide height is the water over a spot. A negative depth is ground that dries at low tide. Land starts at mean high water springs.

| Source | Its own datum | Converted by | Where the figure comes from |
|---|---|---|---|
| LiDAR | NZVD2016 (stated on LDS layer 122508) | depth = -1.746 - height | See below |
| Multibeam model | "Approximate Lowest Astronomical Tide" (stated on LDS layer 116628) | depth = -height, no shift | Taken as chart datum; see below |
| Chart soundings, contours, depth areas | Chart datum | none | LINZ's standard port datum descriptions say these chart datums are the ones depths on its nautical charts are stated in. The `verdat` attribute on the features themselves is empty. |
| GEBCO | Mean sea level | depth = -height - 1.63 | LINZ standard port tidal levels, Marsden Point: MSL is 1.63 m above chart datum |

**The LiDAR offset.** Chart datum at Marsden Point is defined as 4.816 m below the RNZN benchmark, geodetic code DJM9 (LINZ, [Standard port datum descriptions](https://www.linz.govt.nz/guidance/marine-information/tide-prediction-guidance/standard-port-datum-descriptions)). That benchmark's NZVD2016 height is 3.07 m, third order, authorised 30 November 2018 (LINZ [Geodetic Database, mark DJM9](https://www.geodesy.linz.govt.nz/gdb/?code=DJM9)). So chart datum is 3.07 - 4.816 = **1.746 m below NZVD2016**. Both pages were read on 26 November 2026. The benchmark height is given to the centimetre, so the offset is good to about a centimetre at the port.

One offset is used for the whole box. Chart datum is a tidal level, and the tide is not identical along the coast, so the true offset drifts away from the port. How far was not measured here and nothing is corrected for it. The LiDAR's stated accuracy under water is about 0.5 m at 95% in the shallows and wider with depth.

**How well it checks out.** [seabed-report.md](seabed-report.md) has the numbers for the committed build. In short: where the LiDAR and the multibeam overlap (1,170 cells) the LiDAR reads a median 0.19 m deeper, and 90% of cells agree within 0.43 m. Against charted soundings on flat ground the LiDAR reads about 0.4 m deeper for surveys since 1981 and about 0.7 m deeper for those of 1955 to 1962. Part of that is expected, because a chart shows the shallowest sounding in a patch. The rest could be LiDAR bias, a datum error of a few decimetres, or sand that has moved; these checks cannot tell them apart. A wrong offset of a metre or more would show clearly, and does not.

**The multibeam datum.** LINZ describes chart datum as a level that "usually approximates" lowest astronomical tide, and its hydrographic surveys are reduced to chart datum, so "Approximate LAT" on the multibeam model is read as chart datum. If the model were on true LAT it would be 0.18 m off (LAT at Marsden Point is 0.18 m above chart datum), against a stated vertical accuracy of 1.7 m. The overlap with the LiDAR supports the choice: shifting the model by 0.18 m would widen the gap between them from 0.19 m to 0.37 m.

## Depth: the merge

Each cell takes the first source in this order that has a value. `depth_source` records which.

1. **LiDAR, March 2025.** The LINZ coastal topo-bathymetric surveys "Whangārei to Bream Bay" and "Mangawhai to Snells", 10 m DEM. A cell's depth is the mean of its 10 m cells that are sea, and it needs at least half the cell to be sea with data. LiDAR deeper than 40 m below chart datum is dropped (32 cells). Down to 40 m it agrees with charted soundings as well as it does in the shallows (18 soundings between 30 and 40 m, median difference 0.5 m); deeper than that there is no sounding inside the LiDAR's cover to check it against.
2. **Multibeam, 1999 to 2004.** The LINZ "Shipping Lane 1" 20 m depth model (surveys HS6 and HS15), reprojected once from UTM zone 60S to the nested 20 m grid.
3. **Chart soundings and contours.** One triangulated surface through the charted soundings, the depth-contour vertices and the charted coastline (as mean high water springs), tied to the edges of the LiDAR and multibeam so there is no step where they meet, then held inside the charted depth band of each cell (the chart's depth areas say, for example, "5 to 10 m here"). A cell that contains charted soundings takes their mean, whatever the surface or the band says. Three scale bands of chart are used, the finest winning where they overlap. The chart's "quality of data" areas give the year each part was surveyed, which splits these cells into surveyed since 1990 (here, almost all a 2010 survey around the Hen and Chickens), surveyed before 1990 (1955 to 1962, with a little from 1981), and not recorded.
4. **GEBCO** fills any water the charts do not cover. In this box the charts cover everything, so no cell uses it; it stays in the build so that a larger box would not have holes.

The quality class shown on the site follows from the source: *Measured* (LiDAR, multibeam), *Charted* (chart, surveyed since 1990), *Old survey* (chart, before 1990 or undated), *Rough guide* (GEBCO).

## Slope and roughness

Computed on each surveyed source's own fine grid, 10 m for LiDAR and 20 m for multibeam, and only then summarised to the cell, so no gradient is ever taken across the join between two sources. Cells whose depth comes from the chart or GEBCO have neither.

- **Slope**: the mean, over the cell, of the steepest slope at each fine cell (central differences), in degrees.
- **Roughness**: the standard deviation of depth within the cell about its best-fit plane, in metres. A smooth slope scores zero; broken ground scores high.

Roughness from the 20 m multibeam (25 values per cell) is coarser than from the 10 m LiDAR (100 values per cell), and the two should not be compared closely. On flat sand both sources give a slope of about half a degree and a roughness of about 0.06 m. That is the measurement noise, so values near those figures mean "flat and smooth", not a real gentle slope.

## Bottom type

Most specific source first; `bottom_source` records which.

1. **Charted rock**: chart seabed areas marked rock, and charted underwater rocks. Any cell they touch.
2. **Chart seabed samples**: a surveyor's note of the bottom at a point (sand, mud, shell and so on). It sets the one cell it falls in.
3. **DOC Northland habitat map** (Kerr 2010): polygons at a coarse mapping scale. The class of the polygon at the cell's centre.

The classes are reef or rock, sand, mud or fine sediment, shell, gravel or coarse sediment, **soft sediment (sand or mud not told apart)**, and not mapped. The soft-sediment class is there because the habitat map uses it for most of open Bream Bay; publishing it as sand or as mud would be a guess.

## Distances

Two more 100 m layers are worked out from the ones above, for the habitat index and for the reach of each fishing style (`scripts/seabed/distance.py`):

- **Distance to the nearest reef**: metres from each cell's centre to the centre of the nearest cell of reef or rock, 0 on reef.
- **Distance to the mainland shore**: metres to the nearest cell of land that is not an island. Mainland is every piece of land that runs off the edge of the grid; the Hen and Chickens, Sail Rock and the harbour's islets lie wholly inside it.

Both are between cell centres, so they come in steps of a cell.

## The 20 m drawing grid

A 100 m cell is a hectare. Painted on a map zoomed in to a few metres a pixel it is a blur or a staircase, and it throws away what the LiDAR and the multibeam measured and the outlines the chart and the habitat map draw. So the same sources, in the same order of trust, are laid out again on 20 m cells (`scripts/seabed/drawing.py`), 1,930 columns by 1,920 rows:

- **Depth** is the LiDAR (its 10 m cells in fours) or the multibeam where a 20 m cell has one of its own. Everywhere else it is the surface through the charted soundings and contours, the same surface as on the 100 m grid, read at 20 m and held inside the chart's depth areas as drawn at that scale. Within a few cells of a survey the charted water slides to the survey's own nearest depth, so there is no step at the join. The finished surface is smoothed lightly (a Gaussian of one cell), because survey noise of a few centimetres on flat sand would otherwise end every depth band in a speckled fringe.
- **The shoreline** is the edge of the survey where a survey reaches the shore, and elsewhere the chart's coastline rasterised at 20 m. The LiDAR tiles carry no land, so it cannot be taken from them alone.
- **Bottom type** keeps the outlines of charted rock areas and of the habitat map as they are drawn. A charted rock or a seabed sample is a note at a point: it is drawn as a dot on the 100 m cell it speaks for.
- **Contours** are drawn from this depth, so the lines sit on the colour steps.

The grid runs five cells past the shore, repeating the nearest water, and marks those cells by adding 128 to the source code. The map draws its own land (the OpenStreetMap coastline) over the seabed layers, so that coastline is the one seen, with no gap or overlap where it and the chart's differ by a few tens of metres. A tap reads nothing from the fringe.

Once the browser has the drawing grid, a tap reads depth, bottom type and their sources from it, so the popup agrees with the colour under the finger. Slope and roughness are always the 100 m cell's.

The drawing grid adds no information to the charted water, where there is none to add. *How sure the depth is* still says which is which.

## File format

Each `.bin.gz` is the grid's values as unsigned integers, row by row from the north-west corner, little-endian, gzip-compressed. Stored 0 always means "nothing here". For depth, slope, roughness and the distances the manifest gives `scale` and `offset`: value = offset + scale × stored. The other layers store class codes listed in the manifest.

The 20 m depth has 25 times the cells, so it is stored as what is left after guessing each cell from its neighbours (`to_bytes_predicted` in `scripts/seabed/publish.py`; the manifest calls this `"predictor": "plane"`). The guess is west + north - north-west; the difference, modulo 65,536 as a signed number, is folded to an unsigned one (0, -1, 1, -2 become 0, 1, 2, 3); all the low bytes are written first, then all the high bytes. That is 550 kB in place of 1.25 MB. The browser fetches the drawing grid only once the map is zoomed in.

The browser reads them in `web/src/seabed.ts` and paints them, a map tile at a time and at the resolution of the screen, in `web/src/paint.ts`. `src/breamfish/grids.py` reads the 100 m layers with the standard library. It converts a tapped longitude and latitude to NZTM itself, and checks that arithmetic against five points in the manifest that were computed by PROJ before it trusts any tap. Reading a grid in Python needs only the standard library:

```python
import array, gzip, json

manifest = json.load(open("web/public/seabed/manifest.json"))
depth = array.array(
    "H", gzip.open("web/public/seabed/depth.bin.gz").read()
)  # on a little-endian machine
layer, ncols = manifest["layers"]["depth"], manifest["grid"]["ncols"]
metres = layer["offset"] + layer["scale"] * depth[row * ncols + col]  # if the stored value is not 0
```

## Limits

- **Not for navigation.** The charts say so and so does the site.
- A 100 m cell is a mean over a hectare, and slope, roughness and the habitat index are worked out on those. The drawing grid shows features down to about 40 m where the LiDAR or the multibeam measured them; a pinnacle or a hole smaller than that does not show.
- Away from the LiDAR and the multibeam, depth is drawn between charted soundings: about a third of the water. About 8% rests on surveys of 1955 to 1962, mostly a strip between the LiDAR and the multibeam in the south of the bay and a patch north of Bream Head.
- Bottom type away from charted rock is only as good as a 2010 habitat map compiled at a coarse scale.
