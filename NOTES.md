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
