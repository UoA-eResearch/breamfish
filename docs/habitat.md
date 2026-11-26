# The snapper habitat index

Stage 2 of the [roadmap](roadmap.md). The map colours the bay by how well each 100 m square suits snapper in each season, and the [methods page](../web/methods.html) on the site sets out what that rests on.

It is a **habitat index, not a catch forecast**. It ranks places within the bay. It does not know how many snapper there are, and nothing in it responds to the day's tide, wind or water temperature. That is stage 3.

## What it is built from

Three factors, each turning one thing known about a square into a suitability from 0 to 1:

| Factor | Reads | Changes with season | How sure |
|---|---|---|---|
| Depth | the `depth` grid | yes: one curve per season | moderate in spring and summer, low in autumn and winter |
| Bottom type | the `bottom` grid | no | low |
| Distance from reef | the `reef_distance` grid | no | low |

The curves, the scores and the evidence for each are in one file, [`src/breamfish/species/snapper.toml`](../src/breamfish/species/snapper.toml). Each curve there has two paragraphs: `basis`, what is published, and `judgement`, what was decided here because nothing is published. Each piece of evidence cites a reference, and each reference says how much of it was read: the full text, the abstract, or a description in another source. A test (`tests/test_habitat.py`) refuses a curve with no basis or a citation with no reference.

The roadmap called for YAML. The file is TOML because Python reads TOML from its standard library, and the server installs nothing beyond the runtime dependencies.

Snapper here means larger fish, of about 27 cm and over. That is the size most of the studies sort at (they give it as the minimum legal size at the time); the site gives the length and does not state a size limit. Small snapper live differently (harbours, seagrass, structure on soft bottom), and the studies of them are not the ones the scores lean on.

## How it is combined

The index is the weighted geometric mean of the factors, so one poor factor cannot be averaged away by two good ones, and each square can show what each factor contributed. The weights are equal: nothing published says how to rank the factors against each other here. Where the bottom type is not mapped (about an eighth of the water), that factor is left out for the square and the other two carry it.

Suitabilities are stored in 200 steps, and the index is worked out from the stored values, so the factor bars a tap shows are exactly the numbers the index was made from.

## Five classes, cut season by season

The site shows five classes, not a figure. The classes are cut within each season, a fifth of that season's rated water to each as nearly as can be. "Highest" is the best fifth of the bay for that time of year.

They are not cut across the year, and that is deliberate. A season's depth curve gives the shape of that season, not how one season compares with another. The winter curve is nearly flat because almost nothing is known about winter, and pooling the seasons made winter look like the best time everywhere.

Water with the same index always shares a class. Where a curve is flat, a third of the bay can have one index; that block goes to the class its middle falls in (`habitat.fifths`), so a large block of average water is classed as the middle and a class can be much larger or smaller than a fifth, or empty.

## Where it is not shown, and reach

- Water inside the no-take marine reserve is not rated. The mask is the reserve polygon in `web/public/layers/reserves.geojson`, by cell centre.
- For kayak fishing, water more than 3 km from the mainland shore is greyed out. For shore fishing everything beyond 150 m is greyed out, and the shore is drawn as a line of points, each rated by the mean index of the water within reach of it. The distances are in `config.REACH_M`. They are round figures chosen here, not rules or safety limits.
- Islands do not count as shore. Mainland is every piece of land that runs off the edge of the grid (`scripts/seabed/distance.py`).

The roadmap asked for reach along *accessible* shoreline. Whether a stretch of shore can be reached on foot is not checked yet; the site says so.

## How it tests against real records

The index is not built from records of snapper, so the few public ones can test it. [`src/breamfish/species/snapper_records.csv`](../src/breamfish/species/snapper_records.csv) holds one row per place and time: tagging stations and research trawl tows from OBIS, and iNaturalist sightings under open licences. `scripts/fetch_habitat_points.py` writes it.

Each record is compared with the index of its own season. The measure is AUC: the chance that the index at a recorded place is higher than at a place picked at random from the bay's rated water. 0.5 is chance. The numbers for the committed build are in [habitat-report.md](habitat-report.md) and on the methods page.

Read them knowing that:

- these are places someone caught or saw snapper, not a survey of presence and absence, and trawls cannot fish reef;
- the largest group, tagging in November and December 1993, gives positions to the nearest minute of arc, about 1.5 by 1.9 km. So every place is taken as the mean of the index within 1 km of it (`config.RECORD_WINDOW_M`), and so is everything it is compared with. That tests the broad pattern and nothing finer;
- places snapper are caught are not the same as places snapper are.

Two tests are not done yet. The research trawl records also say where tows caught *no* snapper, which would allow a proper presence-and-absence test. And the 2023 fish atlas (Stephenson et al., Zenodo 7083642) models snapper on a 1 km grid; comparing the two would show where they disagree. The atlas is a 1.8 GB download and has not been fetched.

## Rebuilding

```bash
uv run python scripts/build_habitat.py
```

Standard library only, no network, about two seconds. It reads `web/public/seabed/`, the species file, the reserve and the records table, and writes:

| File | What |
|---|---|
| `web/public/habitat/manifest.json` | Everything the site prints: curves, evidence, references, class boundaries, reach, the test against records |
| `web/public/habitat/snapper_index_<season>.bin.gz` | The index, one grid per season |
| `web/public/habitat/snapper_<factor>[_<season>].bin.gz` | Each factor's suitability |
| `web/public/habitat/reach.bin.gz` | Which fishing styles reach each cell (bits 1 boat, 2 kayak, 4 shore) |
| `web/public/habitat/shore.geojson` | The mainland shore as points, with a class for each season |
| `docs/habitat-report.md` | The numbers of this build |

Run it after `scripts/build_seabed.py`, or after changing the species file, the reserve or the records, and commit the output with the change. `tests/test_habitat_build.py` rebuilds from what is committed and fails if the committed grids are out of date.

To refresh the records (rarely needed; the sources hardly change):

```bash
python3 scripts/fetch_habitat_points.py
```

It keeps the raw answers under `data/habitat/raw/` (not committed) and needs the network only for what is missing there.

## Where the code is

- `src/breamfish/habitat.py`: the formula. Curves, the geometric mean, the classes, AUC. The only place the index is worked out. Standard library only, so stage 3 can run it on the server.
- `src/breamfish/grids.py`, `src/breamfish/nztm.py`: reading the byte grids and projecting points, again without numpy.
- `scripts/build_habitat.py`: the hand-run build.
- `web/src/habitat.ts`: reads and paints the grids. It works out nothing: a class is read from the stored index and the stored boundaries.
- `web/src/methods.ts`, `web/methods.html`: the methods page, laid out from the manifest.

## Limits

- It ranks places within the bay and says nothing of how many snapper are in it. In the November 2020 trawl survey the stratum from Bream Bay to Cape Rodney held fewer snapper for its area than any other part of the survey.
- No study has measured snapper by depth in autumn or winter in this stock since 1966, or in Bream Bay in any season.
- Seasonal movement differs on reef and on open ground (trawl catches on soft ground peak in spring, counts at reef edges in autumn). One depth curve per season cannot show both.
- No study compares adult snapper across bottom types by one method at one depth, and none counts them at increasing distance from reef.
- The squares are 100 m, and bottom type away from charted rock is a 2010 habitat map drawn at a coarse scale. A reef that the chart and that map miss is missing here.
- Two studies found that small structure on soft bottom matters more to snapper than whether it is sand or mud. No map of this bay shows that structure.
