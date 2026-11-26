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
