# The seabed layer

Stage 1 of the [roadmap](roadmap.md), with the shaded relief and the rough-ground layer of stage 2c. The site shows depth, how far that depth can be trusted, bottom type and depth contours, and a tap on the water reads them for one spot. Where the depth was measured the map is shaded, so the seabed shows as shapes. The snapper habitat index ([habitat.md](habitat.md)) is built on these grids.

There are two sets of grids. The **100 m grid** is the one every computed number comes from: slope, roughness, the distances, and the habitat index. The **20 m drawing grid** is the same sources laid out five times finer, for the map to paint when zoomed in and for a tap to read. Nothing is computed from the drawing grid.

Everything here is static. `scripts/build_seabed.py` and `scripts/build_relief.py` are run by hand on a development machine, and their outputs are committed under `web/public/seabed/` and `web/public/tiles/`. The server never runs them and never installs the libraries they need.

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

The relief and the rough-ground layer are a second build, run after the first:

```bash
uv run python scripts/build_relief.py
```

It needs no key. The first run fetches the five 2 m LiDAR sheets (130 MB) from the public bucket into the same cache; it reads the multibeam model the first build cached, and the committed grids for which cells are the LiDAR's and what the maps say the bottom is. It takes under a minute, and writes:

| File | What |
|---|---|
| `web/public/tiles/relief_lidar.pmtiles` | Shaded relief from the 2 m LiDAR, zoom 9 to 16 (15.2 MB) |
| `web/public/tiles/relief_multibeam.pmtiles` | Shaded relief from the 20 m multibeam model, zoom 9 to 14 (0.9 MB) |
| `web/public/seabed/fine_roughness.bin.gz` | Rough ground on the 100 m grid |
| `web/public/seabed/manifest.json` | Its own two entries, `relief` and `layers.fine_roughness`; the rest is left as it was |
| `docs/seabed-report.md` | Its last section, on rough ground |

There is one manifest and one report, with two writers. Each build keeps what the other wrote: `build_relief.py` changes only its own entries and its own section, and `build_seabed.py` carries them over when it writes the rest again. After a seabed rebuild they are out of date until `build_relief.py` has been run, and `tests/test_seabed_relief.py` fails if the committed relief no longer matches the committed grids. Unlike the seabed build it does not touch the manifest's `built` date, so the habitat index does not need rebuilding after it.

The same inputs give byte-identical archives. Each rebuild that changes them adds their full size to the repository's history, so do not rebuild them idly.

The code is in `scripts/seabed/`: `grid.py` (the grid), `depth.py` (datums, merge, slope, roughness), `bottom.py` (bottom type), `distance.py` (distance to reef and to the mainland shore), `drawing.py` (the 20 m drawing grid), `relief.py` (shading and rough ground), `tiles.py` (map tiles and their archives), `sources.py` (downloads), `publish.py` (file formats), `report.py` (the checks). `tests/test_seabed_*.py` cover them without touching the network; `tests/test_seabed_build.py` and `tests/test_seabed_relief.py` run the two builds on made-up scenes.

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

## Shaded relief

Depth colours say how deep the water is; they do not show the shape of the bottom. A reef a few metres high in 20 m of water sits inside one colour band. So where the depth was measured the map lays light and shadow over whatever layer is showing (`scripts/seabed/relief.py`). It is flat shading: the map is not tilted.

**Only measured water is shaded.** LiDAR sea no deeper than the 40 m the LiDAR is trusted to, and the multibeam where the LiDAR does not cover at least half of a 20 m square. Charted water, about a third of the sea, has none. Between soundings the surface is a guess, and shading a guess would draw reefs nobody measured. So the edge of the shading is also the edge of the surveys, and a patch of unshaded water inside a survey is a hole in it.

**Each survey is shaded on its own grid**, the LiDAR at 2 m and the multibeam at 20 m, so no slope is taken across the join between them. The LiDAR is read and shaded in blocks of 4 km with a halo, so the seams between blocks do not show.

How it is drawn is judgement, made by looking at the result:

- **Heights are multiplied by 8.** The bay is very flat. The open seabed slopes at well under a degree and most reef edges at a few degrees, which a light 45° up barely tells from level ground.
- **Three lights**, from 315° (half the light), 255° and 15° (a quarter each), all 45° above the horizon. Light from the north-west is the mapping convention that keeps a hill from reading as a hollow. On gentle ground the three add up to one light from the north-west; on steep ground a face turned right away from the main light still catches one of the others, so the shadow side of a reef keeps some shape.
- **Depths are smoothed before the slope is taken**, by a Gaussian of 3 m for the LiDAR and 20 m (one cell) for the multibeam. A LiDAR sounding is good to a few centimetres at best, and over 2 m that is a slope of a degree or more.
- **Weak shade is left out.** Shade under a tenth of full strength is dropped and the rest stretched over what is left. That is about what the LiDAR's noise still shades to on flat sand. It also keeps the archives small: a tile of flat seabed is empty and is not stored.
- A shadow is as strong as a highlight on gentle ground, so a low sand ridge shows both sides. Deep shadow is eased towards black and not cut off at it.

A face much steeper than the light is high cannot catch it squarely. With heights multiplied by 8, ground that really slopes at more than about 23° is darker than level ground even when it faces the light, and ground turned 45° from the light from about 10°. So steep reef reads as dark, textured ground with bright edges where it eases off. That is the exaggeration, not the water.

**Is the multibeam's texture real?** Mid-bay the multibeam shows long ridges running north-east, which could have been survey lines. Where both surveys measured the same seabed (21,617 squares of 20 m), the LiDAR's shade averaged to 20 m and the multibeam's own have a correlation of 0.84. The surveys are twenty years apart and made by different means, so the shapes are the seabed's. The multibeam also carries faint straight stripes along its survey lines; most fall under the tenth that is left out.

**The tiles.** Each pixel is black with some transparency (shadow) or white with some transparency (light), in 31 steps of each, so one set of tiles sits over every layer in the light theme and the dark one. Tiles are 256 pixel PNGs with a palette, in Web Mercator, in two [PMTiles](https://docs.protomaps.com/pmtiles/) archives (`scripts/seabed/tiles.py`): the same single-file format the basemap uses, read a few kilobytes at a time with no tile server. The LiDAR goes to zoom 16, where a pixel is 1.9 m on the ground at this latitude: the LiDAR as it comes, and what the map's closest view is drawn from. The multibeam goes to zoom 14, a pixel of 7.7 m, and the map stretches it from there in. The finest zoom is resampled once from the shade; each coarser zoom is the mean of the four pixels under each of its own. The manifest records each archive's size and a version taken from its contents, which the map adds to the address it asks for, so a browser never reads a rebuilt archive through a cached piece of the old one.

The map draws the relief over the painted layer, under the contours and under its own land.

## Rough ground

The roughness layer above is the spread of depth about one plane through a whole hectare, from 10 m cells. The rough-ground layer (`fine_roughness` in the manifest) looks at the scale of a patch of reef:

1. For each 10 m square of the 2 m LiDAR, the spread (RMS) of its 25 depths about their best-fit plane, in metres. A smooth slope scores zero. A square needs depth in at least 15 of its 25 cells.
2. For each 100 m cell, the **third roughest** of its hundred squares. A patch of reef is often far smaller than a hectare, and a mean or a median loses it in the sand around it; the third roughest and not the roughest, so that one stray return (a moored boat, a school of fish) does not mark a hectare. A cell needs at least half its squares.

It exists only for cells whose depth is the LiDAR's: 27,302 of them. The multibeam's 20 m cells are too coarse for it.

A tap shows it, and *Rough ground* in the layer list colours the water by it in steps of 0.10, 0.15, 0.20 and 0.30 m. **Nothing is built from it.** It does not enter bottom type, distance to reef or the habitat index.

**How well it finds rock** is in [seabed-report.md](seabed-report.md), against two sets of labels, neither of them the truth. For the committed build:

- Cells the chart marks as rock have a median of 0.34 m; cells with a charted sample of sand or mud, 0.04 m. The chance that a rock cell scores higher than a sand or mud one (the AUC) is 0.93 on the chart's labels and 0.95 on the habitat map's.
- That is about as good as the roughness the 100 m grid already had (0.92 and 0.93), and no better on the chart's labels. Looking finer did not buy much.
- The choice of the third roughest square was made after seeing these numbers. The report lists the others: the roughest square scores 0.943, the third roughest 0.929, the tenth roughest 0.885, the mean 0.863, the median 0.781. The fewer squares a summary rests on, the better it finds charted rock, which says charted rock is often a small part of its cell.
- With a line at 0.10 m, 75% of charted rock cells are over it and 9% of sand and mud samples. A quarter of "rock" cells read as smooth. Part of that is the labels: a cell is marked rock if a charted rock area touches any corner of it.
- The same line marks 2,793 cells (11%) of what the habitat map calls soft sediment. Some of that is reef the map misses, which is what the layer is for. Some is sand waves, channel edges and noise.
- **The floor rises with depth.** Flat sand scores a median of 0.04 m in the shallows and 0.09 m at 30 to 40 m, because the LiDAR's returns get noisier as the water deepens. One line for all depths would be wrong at one end.

**As a fourth source of bottom type.** The numbers do not support overruling a chart or a sample with it. They would support a source below the three there are, for water those leave as soft sediment or unmapped, as a class of its own ("rough ground, likely reef") and not as rock, with a line that rises with depth. Whether that improves the habitat index has not been tested, and it stays out until it has.

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
- A 100 m cell is a mean over a hectare, and slope, roughness and the habitat index are worked out on those. The drawing grid shows features down to about 40 m where the LiDAR or the multibeam measured them; a pinnacle or a hole smaller than that does not show in the depth colours. The relief shows shapes down to a few metres across where the LiDAR measured them, and about 40 m where only the multibeam did.
- The relief is a picture, not a measurement. Heights are exaggerated eight times, steep ground is dark whichever way it faces, and unshaded water is not flat water: it may be charted water, where the shape is not known.
- Rough ground is not a bottom type. Sand waves and channel edges are rough, and a flat rock platform is smooth.
- Away from the LiDAR and the multibeam, depth is drawn between charted soundings: about a third of the water. About 8% rests on surveys of 1955 to 1962, mostly a strip between the LiDAR and the multibeam in the south of the bay and a patch north of Bream Head.
- Bottom type away from charted rock is only as good as a 2010 habitat map compiled at a coarse scale.
