# Snapper habitat index: what this build holds

Written by `scripts/build_habitat.py` on 2026-11-26. Do not edit by hand; the method is in [habitat.md](habitat.md).

- Water rated: 102,874 cells of 100 m (of 102,900; 26 are inside the no-take reserve and are not rated).
- Bottom type not mapped, so left out of the index there: 12,952 cells.
- Within reach: kayak 24,689 cells, shore 1,832 cells; 1,832 points along the shore.

## Share of the rated water in each class, by season

A boundary is the lowest index in the class above it. Water with the same index shares a class, so a class is larger or smaller than a fifth where much of the bay has one index, and "none" marks a class nothing reaches.

| Season | Boundaries | Lowest | Low | Middle | High | Highest |
|---|---|---|---|---|---|---|
| Summer | 0.375, 0.440, 0.475, 0.620 | 20% | 20% | 18% | 19% | 23% |
| Autumn | 0.555, 0.575, 0.580, 0.620 | 20% | 16% | 34% | 7% | 23% |
| Winter | 0.570, 0.620, 0.625, 0.630 | 20% | 20% | 38% | 0% | 22% |
| Spring | 0.370, 0.435, 0.495, 0.610 | 20% | 21% | 21% | 19% | 20% |

## Mean suitability of each factor over the rated water

| Factor | Mean |
|---|---|
| depth (summer) | 0.49 |
| depth (autumn) | 0.76 |
| depth (winter) | 0.86 |
| depth (spring) | 0.48 |
| bottom | 0.62 |
| reef | 0.44 |

## Against the places snapper were recorded

AUC is the chance that the index at a place snapper were recorded is higher than at a place picked at random from the bay's rated water in the same season. 0.5 is no better than chance. With no skill, 0.4 of the places would fall in the top two fifths.

233 places and times are in the table. 9 give no month and 2 have no rated water within 1000 m; those are not used.

| Records | Season | Places | AUC | 95% interval | In the top two fifths |
|---|---|---|---|---|---|
| Caught for tagging (Ministry for Primary Industries tag database) | Summer | 57 | 0.64 | 0.56 to 0.70 | 67% |
| Caught for tagging (Ministry for Primary Industries tag database) | Autumn | 26 | 0.61 | 0.48 to 0.74 | 62% |
| Caught for tagging (Ministry for Primary Industries tag database) | Winter | 17 | 0.38 | too few | 35% |
| Caught for tagging (Ministry for Primary Industries tag database) | Spring | 25 | 0.58 | 0.44 to 0.71 | 60% |
| Caught for tagging (Ministry for Primary Industries tag database) | All | 125 | 0.58 | 0.53 to 0.64 | 60% |
| Research trawl tows that caught snapper (NIWA) | Summer | 9 | 0.65 | too few | 67% |
| Research trawl tows that caught snapper (NIWA) | Autumn | 6 | 0.60 | too few | 67% |
| Research trawl tows that caught snapper (NIWA) | Winter | 23 | 0.52 | 0.43 to 0.61 | 48% |
| Research trawl tows that caught snapper (NIWA) | Spring | 52 | 0.64 | 0.55 to 0.71 | 65% |
| Research trawl tows that caught snapper (NIWA) | All | 90 | 0.61 | 0.55 to 0.67 | 61% |
| Photographed by divers and anglers (iNaturalist) | Summer | 5 | 0.88 | too few | 100% |
| Photographed by divers and anglers (iNaturalist) | Winter | 1 | 0.00 | too few | 0% |
| Photographed by divers and anglers (iNaturalist) | Spring | 1 | 0.97 | too few | 100% |
| Photographed by divers and anglers (iNaturalist) | All | 7 | 0.77 | too few | 86% |
| All records | All | 222 | 0.60 | 0.56 to 0.64 | 61% |

Cautions:

- These are places someone caught or saw snapper, not a survey of where snapper are and are not. Tagging boats and trawlers work ground that suits their gear: trawls cannot fish reef.
- Most of the tagging records are one programme in November and December 1993, and their positions are given to the nearest minute of arc, about 1.5 km by 1.9 km. Each place is therefore compared as the average of the index within 1 km of it, which blurs anything finer.
- Places fishing is good are not the same as places snapper are: gear, bait, tide and time of day decide a catch.
