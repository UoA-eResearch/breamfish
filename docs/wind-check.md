# The 1 km wind forecast against measured wind

How our own 1 km wind forecast (run on the cluster; see "Where a cluster helps" in [roadmap.md](roadmap.md)) compares with the public forecast the site has always drawn, against wind that was measured. The cluster reruns this every day after the night's forecast and publishes it next to the forecast as `wind/check.md`; this page is a copy taken by hand, with what it means.

## How it is made

- **Measured wind**: Whangarei Aerodrome (WMO 93057), hourly, from the synoptic reports Ogimet archives; and Northport's stations in the harbour, every ten minutes since 28 November 2026. None of these is over the open bay: the aerodrome is inland at the head of the harbour, 38 m up, and Northport's are in or beside the harbour. They test both forecasts at the bay's edge.
- **Our forecast**: the scheduled runs, and hindcasts: the same model started from the GFS forecasts of past days, so that it can be scored against wind already measured.
- **The public forecast**: Open-Meteo's own record of what it forecast on each day (its Previous Runs service), so the two are compared at the same lead.
- **Lead day 0** is the day the forecast began (UTC), lead day 1 the next. Only hours where both forecasts and a measurement exist are used.
- The script, with every definition, is `check-wind.py` in the cluster repository.

## First result (28 November 2026, one forecast)

| Where | Lead day | Hours | Forecast | Bias kn | Speed error kn | Vector error kn | Direction error ° (hours) |
|---|---|---|---|---|---|---|---|
| All stations | 0 | 21 | ours, 1 km | -1.3 | 1.4 | 2.9 | 28 (5) |
| All stations | 0 | 21 | public, Open-Meteo | -0.5 | 0.9 | 3.4 | 19 (5) |

Too little to say anything: one forecast, 21 hours, and only five of them with a wind of 5 kn or more. Hindcasts for 22 to 27 November are running and will add several hundred hours.
