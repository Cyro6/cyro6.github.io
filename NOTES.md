# Site Notes

## Data Update Workflow

### 1. Refresh from Google Sheets
```
python update_data.py
```
Downloads the latest trip, campsite, and stream info data from Google Sheets and writes `assets/data/streams.json`. Automatically reapplies any cached weather data from `weather_cache.json`.

### 2. Fill missing weather data (if new trips were added)
```
python fill_weather.py
```
Fetches historical weather (temperature, precipitation, wind, pressure) from the Open-Meteo ERA5 API for any trips that have GPS coordinates but no logged weather. Groups by location to minimize API calls. Saves results to both `streams.json` and `weather_cache.json`.

Only needs to run when new trips have been added that are missing weather. Existing cached entries are not re-fetched.

**Note:** 224 trips have blank/zero coordinates in the sheet and cannot be auto-filled. Add real coordinates to those rows in the sheet first, then re-run.

### Targeted updates (faster alternatives to full pipeline)

**Refresh campsites only** — pulls latest campsite data from the Google Sheet Campgrounds tab without re-downloading everything else:
```
python update_data.py --campsites-only
```

**Rebuild stream→DNR name mapping** — re-runs GPS proximity matching to re-link user stream names to DNR geometry names. Uses only local files (no network calls). Run this if stream lines appear in wrong locations on the map:
```
python update_data.py --name-map
```
Note: `MANUAL_OVERRIDES` in `update_data.py` ensures problem streams (e.g. Harvey Creek) survive a re-run.

**Regenerate bridge crossings** — rebuilds `assets/data/bridge_crossings.json` from the local DNR stream segments. Only needs to run if stream geometry changes:
```
python update_data.py --bridges-only
```

### 3. Commit and push
```
git add assets/data/
git commit -m "Refresh data"
git push
```

---

## Key Files

| File | Purpose |
|---|---|
| `update_data.py` | Downloads Google Sheets → `streams.json` |
| `fill_weather.py` | Backfills weather for trips with GPS coords |
| `assets/data/streams.json` | Main data file used by all pages |
| `assets/data/weather_cache.json` | Cached weather keyed by date+location — survives sheet re-downloads |
| `assets/data/bridge_crossings.json` | Road–stream bridge locations near trout streams (from OpenStreetMap) |

---

## Map — Live Stream Conditions

The **Live Conditions** button in the map controls fetches 7-day accumulated precipitation for every visible stream and recolors the stream lines by runoff risk.

### How it works

1. **Grid grouping** — Each stream's GPS coordinates are rounded to the nearest 0.5° lat/lon. Streams that fall in the same cell share one API call, which keeps the request count low (typically 10–20 cells for all of Wisconsin).

2. **API call** — For each unique grid cell, one request is made to the [Open-Meteo forecast API](https://open-meteo.com):
   ```
   https://api.open-meteo.com/v1/forecast
     ?latitude=…&longitude=…
     &daily=precipitation_sum
     &past_days=7&forecast_days=0
     &precipitation_unit=inch
     &timezone=America/Chicago
   ```
   Returns the last 7 days of daily precipitation totals. These are summed into a single "7-day total" per cell.

3. **Color thresholds** — Stream lines are recolored based on the 7-day total for their grid cell:

   | Total | Color | Label |
   |---|---|---|
   | < 0.5" | Green | Dry |
   | 0.5–1.5" | Amber | Elevated |
   | 1.5–2.5" | Orange | High Risk |
   | > 2.5" | Red | Likely Blown Out |
   | No data | Gray | — |

4. **Forecast presets** — After fetching, **Today / +3d / +7d / +14d** buttons appear. Each preset shows the **7-day accumulated precipitation window ending on that date** — a mix of past actuals and forecast depending on how far out:

   | Preset | Past days included | Forecast days included |
   |---|---|---|
   | Today | 7 | 0 |
   | +3d | 4 | 3 |
   | +7d | 0 | 7 |
   | +14d | 0 | 7 (max; limited by free tier) |

   The intent is "how saturated will the watershed be by the time I get there" — not just how much it will rain between now and then. Each preset result is cached separately; switching between presets after the first fetch is instant.

5. **Popup** — Clicking a stream in conditions mode shows the exact total, the window label, and the risk level instead of the normal rating popup.

6. **Caching** — Each offset is fetched once per page load and cached. Toggling conditions off and back on reuses cached results. Refreshing the page clears all caches.

### Limitations
- Precipitation is at 0.25° resolution (~17 miles), so nearby streams share the same value.
- Does not account for terrain, snowmelt, or upstream watershed size — it is purely a rainfall accumulation indicator.
- Forecast limit is ~16 days on the Open-Meteo free tier; +14d is near that ceiling.

---

## Pages

| URL | Description |
|---|---|
| `/Analytics` | Stream performance table with filters |
| `/planner` | Trip planner with campsite proximity and precipitation |
| `/insights` | Hub linking to all 5 data visualization pages |
| `/insights-weather` | Weather condition vs avg rating charts |
| `/insights-heatmap` | Stream × month performance heatmap |
| `/insights-trends` | Rating over time, year averages, seasonal patterns |
| `/insights-compare` | Side-by-side comparison of up to 3 streams |
| `/insights-precip` | Day-of and 3-day prior precipitation analysis |
| `/insights-moon` | Moon phase and illumination vs avg rating (computed client-side from trip dates) |
| `/stream-details` | Per-stream detail page (linked from Analytics table) |
| `/resources` | Links to external tools, weather, and data sheets |
