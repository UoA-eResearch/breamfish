# Seabed build report

Written by `scripts/build_seabed.py`; do not edit by hand. It describes the grids committed under `web/public/seabed/`. The method is in [seabed.md](seabed.md).

Differences are grid minus sounding, in metres: positive means the grid is deeper. A cell is a mean over one hectare and a sounding is one point, usually the shallowest in its patch, so a small positive difference is expected.

## Where the depth comes from (102,900 sea cells of one hectare)

| Source | Cells | Share of sea |
|---|---|---|
| Airborne LiDAR, March 2025 | 27,559 | 26.8% |
| Multibeam sonar, 1999 to 2004 | 39,882 | 38.8% |
| Chart soundings, surveyed since 1990 | 26,663 | 25.9% |
| Chart soundings, surveyed before 1990 | 8,682 | 8.4% |
| Chart soundings, survey date not recorded | 114 | 0.1% |
| Global grid (GEBCO) | 0 | 0.0% |

| Quality class | Cells | Share of sea |
|---|---|---|
| Measured | 67,441 | 65.5% |
| Charted | 26,663 | 25.9% |
| Old survey | 8,796 | 8.5% |
| Rough guide | 0 | 0.0% |

Slope and roughness exist for 66,598 cells (64.7%).

## LiDAR against charted soundings

Every charted sounding that falls in a cell the LiDAR covers, before any depth limit is applied.

| Sounding depth (m) | Soundings | Median difference (m) | Median size (m) | 90% within (m) |
|---|---|---|---|---|
| -5 to 5 | 830 | +0.48 | 0.6 | 2.85 |
| 5 to 10 | 407 | +0.43 | 0.69 | 2.86 |
| 10 to 20 | 450 | +0.69 | 0.81 | 2.26 |
| 20 to 25 | 68 | +1.58 | 1.58 | 2.91 |
| 25 to 30 | 35 | +0.78 | 0.91 | 2.51 |
| 30 to 40 | 18 | +0.51 | 0.55 | 1.42 |

The same soundings against the 10 m LiDAR cell each one falls in, grouped by when the chart says the area was surveyed. Flat ground is where the LiDAR varies by under 0.3 m across the 50 m around the sounding.

| Chart survey | Ground | Soundings | Median difference (m) | Middle half (m) |
|---|---|---|---|---|
| 1955 to 1962 | all | 624 | +0.77 | +0.37 to +1.27 |
| 1955 to 1962 | flat | 183 | +0.71 | +0.34 to +0.93 |
| 1981 to 1982 | all | 430 | +0.40 | +0.16 to +0.64 |
| 1981 to 1982 | flat | 147 | +0.41 | +0.25 to +0.54 |
| 1999 on | all | 732 | +0.45 | +0.22 to +0.74 |
| 1999 on | flat | 59 | +0.37 | +0.18 to +0.57 |

LiDAR deeper than 40 m below chart datum is not used: 32 cells were dropped for that reason.

## Multibeam against charted soundings

| Sounding depth (m) | Soundings | Median difference (m) | Median size (m) | 90% within (m) |
|---|---|---|---|---|
| 10 to 20 | 12 | +0.09 | 0.25 | 0.51 |
| 20 to 25 | 7 | -0.05 | 0.3 | 0.87 |
| 25 to 30 | 28 | +1.30 | 1.45 | 3.45 |
| 30 to 40 | 80 | +0.59 | 0.63 | 1.8 |
| 40 to 60 | 308 | +0.54 | 0.56 | 1.16 |
| 60 to 200 | 36 | -0.01 | 0.25 | 0.58 |

## LiDAR against multibeam

The two overlap in 1,170 cells. LiDAR minus multibeam: median +0.19 m, median size 0.2 m, 90% within 0.43 m.

## The merged grid against charted soundings

All sources together. Where the depth is from the chart this is not an independent test: the surface was drawn through these soundings.

| Sounding depth (m) | Soundings | Median difference (m) | Median size (m) | 90% within (m) |
|---|---|---|---|---|
| -5 to 5 | 880 | +0.44 | 0.55 | 2.85 |
| 5 to 10 | 475 | +0.36 | 0.59 | 2.83 |
| 10 to 20 | 626 | +0.51 | 0.7 | 2.19 |
| 20 to 25 | 111 | +0.51 | 0.71 | 2.75 |
| 25 to 30 | 98 | +0.00 | 0.11 | 2.6 |
| 30 to 40 | 129 | +0.39 | 0.45 | 1.44 |
| 40 to 60 | 454 | +0.22 | 0.27 | 1.05 |
| 60 to 200 | 145 | +0.00 | 0.0 | 0.31 |

## Spot checks

| Longitude | Latitude | Charted sounding (m) | Grid (m) | Difference (m) | Grid source |
|---|---|---|---|---|---|
| 174.3745 | -35.781 | -0.3 | 0.2 | +0.5 | Airborne LiDAR, March 2025 |
| 174.4856 | -35.9029 | 16.1 | 16.7 | +0.6 | Airborne LiDAR, March 2025 |
| 174.5098 | -35.8363 | 14.8 | 15.6 | +0.8 | Airborne LiDAR, March 2025 |
| 174.656 | -36.1209 | 36.0 | 36.3 | +0.3 | Airborne LiDAR, March 2025 |
| 174.5425 | -35.9141 | 29.0 | 29.6 | +0.6 | Multibeam sonar, 1999 to 2004 |
| 174.6109 | -35.8525 | 58.0 | 58.3 | +0.3 | Multibeam sonar, 1999 to 2004 |
| 174.6618 | -35.8088 | 71.0 | 71.2 | +0.2 | Multibeam sonar, 1999 to 2004 |
| 174.803 | -36.1097 | 56.0 | 56.2 | +0.2 | Multibeam sonar, 1999 to 2004 |
| 174.4004 | -35.7862 | 8.4 | 8.4 | +0.0 | Chart soundings, surveyed since 1990 |
| 174.513 | -35.8385 | 16.3 | 16.3 | +0.0 | Chart soundings, surveyed since 1990 |
| 174.7333 | -35.8997 | 46.0 | 46.0 | +0.0 | Chart soundings, surveyed since 1990 |
| 174.8028 | -35.9034 | 90.0 | 90.0 | +0.0 | Chart soundings, surveyed since 1990 |
| 174.3923 | -35.7817 | 8.3 | 8.3 | +0.0 | Chart soundings, surveyed before 1990 |
| 174.5812 | -35.8637 | 35.0 | 35.0 | +0.0 | Chart soundings, surveyed before 1990 |
| 174.5959 | -35.8323 | 25.0 | 25.0 | +0.0 | Chart soundings, surveyed before 1990 |
| 174.6976 | -36.1214 | 45.0 | 45.0 | +0.0 | Chart soundings, surveyed before 1990 |

## Bottom type

| Class | Cells | Share of sea |
|---|---|---|
| Not mapped | 12,952 | 12.6% |
| Reef or rock | 3,188 | 3.1% |
| Sand | 3,029 | 2.9% |
| Mud or fine sediment | 6,545 | 6.4% |
| Shell | 18 | 0.0% |
| Gravel or coarse sediment | 313 | 0.3% |
| Soft sediment, sand or mud not told apart | 76,855 | 74.7% |

## Rough ground from the 2 m LiDAR

Written by `scripts/build_relief.py`; do not edit by hand. It describes `web/public/seabed/fine_roughness.bin.gz`. The method is in [seabed.md](seabed.md).

The layer has a value for 27,302 cells: those whose depth is the LiDAR's. Each is the third roughest of the cell's hundred 10 m squares, and a square's roughness is the spread of the 2 m LiDAR depths in it about their best-fit plane, in metres. It is published and shown; nothing else is built from it.

The relief tiles from the same build shade 270.0 km² from the LiDAR and 396.8 km² from the multibeam. Where both surveys measured the same seabed (21,617 squares of 20 m), the LiDAR's shade averaged to 20 m and the multibeam's own have a correlation of 0.84. The surveys were made about twenty years apart and by different means, so shapes that both show are the seabed's and not one survey's artefacts.

### By what the maps say the bottom is

Neither map is the truth. The chart marks a cell as rock if a charted rock area touches it or a charted rock stands in it; a seabed sample is one point in the hectare. The habitat map was drawn at a coarse scale.

| Cells | Count | Lowest tenth (m) | Quarter | Median | Three quarters | Highest tenth |
|---|---|---|---|---|---|---|
| Chart: marked as rock | 404 | 0.07 | 0.11 | 0.34 | 0.68 | 0.90 |
| Chart: a sample of sand or mud | 121 | 0.02 | 0.03 | 0.04 | 0.06 | 0.10 |
| Habitat map: rock | 552 | 0.10 | 0.15 | 0.23 | 0.42 | 0.62 |
| Habitat map: sand, mud or soft sediment | 25,469 | 0.03 | 0.04 | 0.05 | 0.07 | 0.11 |
| Every cell with a value | 27,302 | 0.03 | 0.04 | 0.05 | 0.07 | 0.13 |

### How well it separates them

The chance that a rock cell scores higher than a soft one (the area under the ROC curve): 1 is perfect, 0.5 is a coin. The first column is charted rock against charted samples of sand or mud; the second is the habitat map's rock against its soft sediment. Other ways of summarising the same 10 m squares, and the two terrain layers the 100 m grid already has, are scored on the same cells. With this few labelled cells, differences under about 0.02 mean nothing.

| Scored by | Chart labels | Habitat map labels |
|---|---|---|
| Rough ground, as published: the third roughest 10 m square | 0.929 | 0.951 |
| The roughest 10 m square | 0.943 | 0.950 |
| The tenth roughest 10 m square | 0.885 | 0.945 |
| The mean of the 10 m squares | 0.863 | 0.934 |
| The median of the 10 m squares | 0.781 | 0.913 |
| Roughness of the 100 m grid: about one plane through the cell | 0.917 | 0.928 |
| Slope of the 100 m grid | 0.911 | 0.924 |

### If a line were drawn

Cells rougher than each value, of those the maps class each way.

| Rougher than (m) | Of chart rock | Of chart sand or mud | Of habitat map rock | Of habitat map soft sediment |
|---|---|---|---|---|
| 0.10 | 303 (75%) | 11 (9%) | 490 (89%) | 2,793 (11%) |
| 0.15 | 272 (67%) | 5 (4%) | 410 (74%) | 1,210 (5%) |
| 0.20 | 246 (61%) | 3 (2%) | 323 (59%) | 589 (2%) |
| 0.30 | 211 (52%) | 1 (1%) | 204 (37%) | 141 (1%) |

The last column is the rough ground the habitat map calls soft: either reef it misses, or sand waves, channel edges and survey noise.

### The floor rises with depth

Cells not classed as rock, by depth. The LiDAR's returns are noisier in deeper water, so the same flat sand scores higher there, and one line for all depths would be too strict inshore or too loose offshore.

| Depth (m) | Cells | Median (m) | Highest tenth (m) |
|---|---|---|---|
| -3 to 5 | 6,735 | 0.04 | 0.11 |
| 5 to 10 | 3,345 | 0.04 | 0.11 |
| 10 to 20 | 9,535 | 0.05 | 0.07 |
| 20 to 30 | 5,784 | 0.06 | 0.13 |
| 30 to 40 | 939 | 0.09 | 0.21 |

### As a source of bottom type

It tells charted rock from charted sand and mud about as well as the roughness the 100 m grid already has (0.93 against 0.92), and no better. At 0.10 m, 101 (25%) of the cells the chart marks as rock read as smooth, and 11 (9%) of the cells with a sample of sand or mud read as rough. The labels are part of that: a cell is marked rock if a charted rock area touches any corner of it, and a sample speaks for one point of its hectare. Rough ground is a hint that a cell holds reef, not a measurement of what the bottom is made of, and these numbers do not support overruling a chart or a sample with it. They do support a fourth source placed below the three there are: one that classes water they leave as soft sediment or unmapped, as a class of its own (rough ground, likely reef) and not as rock, with a line that rises with depth as the table above shows the floor doing. Until the habitat index has been tested with and without it, it stays out.
