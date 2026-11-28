# Boats seen from space

A map layer, on trial since 28 November 2026: where boats were seen in Bream Bay in
Sentinel-2 satellite pictures, in 1 km squares, for all passes, weekends and holidays,
and weekdays. It says where people take their boats. It is not a count of fish and not
a forecast, and many of the boats it sees are on their way somewhere.

## How it is made

The count runs on the vhpc cluster, by hand. The scripts and the full account are in the
cluster repository (`ansible/playbooks/files/boats/`, and "Counting boats from
Sentinel-2" in its `docs/runbook.md`). In short:

1. **Scenes.** Every Sentinel-2 L2A picture of tile 60HTF with less than 60% cloud, from
   the public archive on AWS through the Earth Search catalogue: 408, from July 2017 to
   November 2026. The satellites pass at about 11:25 New Zealand time.
2. **Candidates.** On clear open water at least 200 m from shore (the scene's own
   classification), spots brighter in near-infrared than the water around them. A
   picture 640 m across is cut around each one. CPU nodes, one scene per job.
3. **Labels.** An open-weights vision model, Qwen3-VL-8B (FP8, Apache 2.0), on the
   cluster's NVIDIA L4, is shown six labelled pictures and then asked of each candidate
   whether it is a boat, cloud, a wave or something else. 47,378 pictures took 1 h 27 min.
4. **Checks.** The model's boat answers are kept only where five checks also pass:
   - the bright spot covers at least 3 pixels (a wake does; most whitecaps do not);
   - its near-infrared peak is at least 0.06 (thin cloud puffs are dimmer);
   - no candidate the model called cloud lies within 1 km in the same picture;
   - the picture has no more than 0.11 candidates per clear 250 m square (rougher seas
     or broken cloud: 75 pictures are left out whole);
   - the 250 m square does not hold a candidate on more than 15% of its clear passes
     (moorings, rocks, buoys).
5. **Squares.** For each 1 km square, the boats seen and the passes on which it was
   clear, for each group of passes. A square clear on fewer than 10 passes on average is
   left off. `boats-map.py` writes this as `site.json` and publishes it to the cluster's
   public results container under `boats/site.json`.
6. **The site's files.** `scripts/build_boats.py` here reads that file, refuses one that
   does not add up, puts each square in a colour band by boats per 100 clear passes
   (up to 1.5, 1.5 to 3, 3 to 6, 6 to 12, over 12; grey for none seen), and writes
   `web/public/boats/boats.geojson` and `manifest.json`. The site draws what is in them
   and works nothing out.

## How well it finds boats

The checks were set by looking at random samples of the boats kept, by eye. This was done
by Claude, the AI assistant that built the count, not by a person.

| Sample of 60 | Certain boat | Likely boat | Cloud or rock | Can't tell |
|---|---|---|---|---|
| The model alone (only its faintest candidates left out) | 11 | 13 | 11 | 25 |
| With the first three checks | 25 | 12 | 15 | 8 |
| With all five: a fresh sample, not used to set them | 34 | 18 | 3 | 5 |

"Certain" means a hull or a wake can be seen; "likely" is a lone bright spot on open
water, which is how a small boat at rest looks at 10 m. So something like 85% of what the
layer counts are boats, and about half are certainly boats. The figures come from 60
pictures each, so they are rough.

Two signs that what is left is mostly boats, apart from the sample: weekends and holidays
have 9.0 boats a pass and weekdays 5.0, and the busiest passes are summer holidays
(3 January 2021, 4 January 2019, 28 December 2024) and Labour Weekend 2019. The model
alone had put rough winter days at the top.

## What it cannot tell you

- Every picture is taken at about 11:25. Dawn, dusk and night are not in it.
- At 10 m a boat is mostly seen by its wake, so boats at anchor or drifting, which is how
  most people fish, are counted less often than boats under way.
- The busiest squares are the harbour channel from Marsden Cove out past the entrance:
  traffic, not fishing.
- Rough and cloudy days are left out, so this is where boats are on fine days.
- Moorings are left out on purpose.
- Most open-water squares hold a few boats in nine years. The pattern is broad; one or
  two boats between neighbouring squares means nothing.

## Rebuilding

When the count has been run again on the cluster:

```bash
uv run python scripts/build_boats.py <address of boats/site.json in the results container>
```

The address is the cluster's `tofu output results_base_url` followed by `boats/site.json`.
Review the diff of `web/public/boats/` and commit it.

## Better pictures

Planet's daily 3 m imagery would show boats at anchor and several times a day's worth of
passes; access has been applied for (28 November 2026). The count would be run again on it
by the same steps.
