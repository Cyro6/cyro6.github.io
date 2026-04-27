"""
fill_weather.py — Backfill missing weather data in streams.json.

Uses Open-Meteo Historical API (free, no key required, ERA5 reanalysis).
Groups trips by location, makes one date-range call per unique location
rather than one call per trip.

Persists results to weather_cache.json so that re-running update_data.py
(which regenerates streams.json from Google Sheets) automatically
reapplies the cached weather without hitting the API again.

Usage:
    python fill_weather.py

Workflow:
    1. python update_data.py      <- refresh from Google Sheets
    2. python fill_weather.py     <- fill + cache weather
    3. git add assets/data/ && git commit && git push
"""

import json, urllib.request, urllib.parse, urllib.error, time, os
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
STREAMS_PATH = os.path.join(BASE_DIR, 'assets', 'data', 'streams.json')
CACHE_PATH   = os.path.join(BASE_DIR, 'assets', 'data', 'weather_cache.json')
API_URL      = 'https://archive-api.open-meteo.com/v1/archive'
DELAY_SEC    = 0.7
MAX_RETRIES  = 3

# Columns in source rows
COL_DATE      = 0
COL_LAT       = 12
COL_LON       = 13
COL_TMIN      = 21
COL_TMAX      = 22
COL_CONDITION = 23
COL_PRECIP    = 24
COL_RAIN3DAY  = 25
COL_WIND_SPD  = 26
COL_WIND_DIR  = 27
COL_PRESSURE  = 28
COL_P_TREND   = 29


def parse_mdy(s):
    p = s.strip().split('/')
    return datetime(int(p[2]), int(p[0]), int(p[1]))


def to_iso(dt):
    return dt.strftime('%Y-%m-%d')


def cache_key(date_mdy, lat_s, lon_s):
    """Stable key: YYYY-MM-DD_lat2_lon2"""
    try:
        p = date_mdy.strip().split('/')
        iso = f"{p[2]}-{int(p[0]):02d}-{int(p[1]):02d}"
        return f"{iso}_{round(float(lat_s), 2):.2f}_{round(float(lon_s), 2):.2f}"
    except Exception:
        return None


def is_valid_coord(lat_s, lon_s):
    try:
        lat, lon = float(lat_s), float(lon_s)
        return abs(lat) > 1 and abs(lon) > 1
    except Exception:
        return False


def degrees_to_cardinal(deg):
    dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
    return dirs[round(float(deg) / 22.5) % 16]


def wmo_to_condition(code):
    c = int(code)
    if c == 0:                           return 'Sunny'
    if c == 1:                           return 'Mostly Sunny'
    if c == 2:                           return 'Partly Cloudy'
    if c == 3:                           return 'Cloudy'
    if c in (51, 53, 55, 56, 57):        return 'Drizzle'
    if c in (61,63,65,66,67,80,81,82,
             85,86,95,96,99):            return 'Rainy'
    if c in (71, 73, 75, 77):            return 'Snow'
    return 'Cloudy'


def pressure_trend_label(morning, evening):
    diff = evening - morning
    sign = '+' if diff >= 0 else ''
    if diff > 3:     return f'Significant Rising ({sign}{diff:.1f} hPa)'
    if diff > 0.5:   return f'Rising ({sign}{diff:.1f} hPa)'
    if diff >= -0.5: return 'Stable'
    if diff >= -3:   return f'Falling ({diff:.1f} hPa)'
    return f'Significant Falling ({diff:.1f} hPa)'


def fetch_api(lat, lon, start, end):
    params = {
        'latitude':  lat,
        'longitude': lon,
        'start_date': start,
        'end_date':   end,
        'daily':  ('temperature_2m_max,temperature_2m_min,precipitation_sum,'
                   'wind_speed_10m_max,wind_direction_10m_dominant,weather_code'),
        'hourly': 'pressure_msl',
        'temperature_unit':  'fahrenheit',
        'precipitation_unit': 'inch',
        'wind_speed_unit':   'mph',
        'timezone': 'America/Chicago',
    }
    url = API_URL + '?' + urllib.parse.urlencode(params)
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'fill_weather/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 15 * (attempt + 1)
                print(f'  Rate limited — waiting {wait}s...')
                time.sleep(wait)
            else:
                raise
        except Exception:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(3)
    return None


def safe_idx(lst, j):
    return lst[j] if lst and j < len(lst) else None


def parse_api_response(wx_data):
    """Return (daily_lookup, pressure_lookup) dicts indexed by ISO date."""
    daily = wx_data.get('daily', {})
    times = daily.get('time', [])
    daily_lookup = {}
    for j, t in enumerate(times):
        daily_lookup[t] = {
            'tmax':       safe_idx(daily.get('temperature_2m_max'), j),
            'tmin':       safe_idx(daily.get('temperature_2m_min'), j),
            'precip':     safe_idx(daily.get('precipitation_sum'), j),
            'wind_speed': safe_idx(daily.get('wind_speed_10m_max'), j),
            'wind_dir':   safe_idx(daily.get('wind_direction_10m_dominant'), j),
            'wcode':      safe_idx(daily.get('weather_code'), j),
        }

    hourly = wx_data.get('hourly', {})
    htimes = hourly.get('time', [])
    hpres  = hourly.get('pressure_msl', [])
    pressure_lookup = defaultdict(dict)
    for j, t in enumerate(htimes):
        date_part, time_part = t.split('T')
        hr = int(time_part.split(':')[0])
        if hr in (6, 12, 18):
            v = safe_idx(hpres, j)
            if v is not None:
                pressure_lookup[date_part][hr] = v

    return daily_lookup, pressure_lookup


def build_wx_record(daily_lookup, pressure_lookup, trip_dt):
    """Build a weather record dict for a single trip date."""
    iso = to_iso(trip_dt)
    d = daily_lookup.get(iso)
    if not d:
        return None

    wx = {}
    if d['tmin']       is not None: wx['tmin']      = str(round(d['tmin'], 1))
    if d['tmax']       is not None: wx['tmax']      = str(round(d['tmax'], 1))
    if d['wcode']      is not None: wx['condition'] = wmo_to_condition(d['wcode'])
    if d['precip']     is not None: wx['precip']    = str(round(d['precip'], 2))
    if d['wind_speed'] is not None: wx['wind_speed']= str(round(d['wind_speed'], 1))
    if d['wind_dir']   is not None: wx['wind_dir']  = degrees_to_cardinal(d['wind_dir'])

    # 3-day prior rainfall sum
    prior = sum(
        (daily_lookup.get(to_iso(trip_dt - timedelta(days=b)), {}).get('precip') or 0)
        for b in (1, 2, 3)
    )
    wx['recent_rain'] = str(round(prior, 2))

    # Pressure at noon + trend
    p_day = pressure_lookup.get(iso, {})
    noon = p_day.get(12)
    if noon is not None:
        wx['pressure'] = str(round(noon, 1))
        morn, eve = p_day.get(6), p_day.get(18)
        if morn and eve:
            wx['pressure_trend'] = pressure_trend_label(morn, eve)

    return wx


FIELD_MAP = [
    (COL_TMIN,      'tmin'),
    (COL_TMAX,      'tmax'),
    (COL_CONDITION, 'condition'),
    (COL_PRECIP,    'precip'),
    (COL_RAIN3DAY,  'recent_rain'),
    (COL_WIND_SPD,  'wind_speed'),
    (COL_WIND_DIR,  'wind_dir'),
    (COL_PRESSURE,  'pressure'),
    (COL_P_TREND,   'pressure_trend'),
]


def apply_to_row(row, wx):
    """Fill empty weather columns. Returns True if anything changed."""
    changed = False
    for col, key in FIELD_MAP:
        if not row[col] and wx.get(key):
            row[col] = wx[key]
            changed = True
    return changed


def main():
    with open(STREAMS_PATH, encoding='utf-8') as f:
        data = json.load(f)
    rows = data['source']['rows']
    print(f'Total rows: {len(rows)}')

    # Load existing cache
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding='utf-8') as f:
            cache = json.load(f)
        print(f'Cache loaded: {len(cache)} entries')
    else:
        cache = {}

    # Pass 1: apply existing cache
    cache_hits = sum(1 for r in rows
                     if not r[COL_TMIN]
                     and apply_to_row(r, cache.get(cache_key(r[COL_DATE], r[COL_LAT], r[COL_LON]), {})))
    print(f'Filled from cache: {cache_hits}')

    # Pass 2: identify rows still missing weather with valid coords
    needs_fetch = [
        i for i, r in enumerate(rows)
        if not r[COL_TMIN] and is_valid_coord(r[COL_LAT], r[COL_LON]) and r[COL_DATE]
    ]
    print(f'Rows needing API fetch: {len(needs_fetch)}')

    if needs_fetch:
        # Group by rounded location
        loc_groups = defaultdict(list)
        for i in needs_fetch:
            r = rows[i]
            loc_groups[(round(float(r[COL_LAT]), 2), round(float(r[COL_LON]), 2))].append(i)

        print(f'Unique locations to fetch: {len(loc_groups)}\n')
        newly_filled = 0

        for g_num, ((lat, lon), indices) in enumerate(sorted(loc_groups.items()), 1):
            trip_dts = []
            for i in indices:
                try:
                    trip_dts.append((i, parse_mdy(rows[i][COL_DATE])))
                except Exception:
                    pass
            if not trip_dts:
                continue

            dates      = [dt for _, dt in trip_dts]
            start_dt   = min(dates) - timedelta(days=4)  # buffer for 3-day prior calc
            end_dt     = max(dates)

            print(f'[{g_num}/{len(loc_groups)}] ({lat}, {lon})  '
                  f'{to_iso(start_dt)} to {to_iso(end_dt)}  ({len(indices)} trips)', end='  ', flush=True)

            try:
                wx_data = fetch_api(lat, lon, to_iso(start_dt), to_iso(end_dt))
            except Exception as e:
                print(f'ERROR: {e}')
                time.sleep(DELAY_SEC)
                continue

            daily_lookup, pressure_lookup = parse_api_response(wx_data)
            count = 0

            for i, trip_dt in trip_dts:
                r = rows[i]
                wx = build_wx_record(daily_lookup, pressure_lookup, trip_dt)
                if not wx:
                    continue
                key = cache_key(r[COL_DATE], r[COL_LAT], r[COL_LON])
                if key:
                    cache[key] = wx
                if apply_to_row(r, wx):
                    count += 1
                    newly_filled += 1

            print(f'-> {count} filled')
            time.sleep(DELAY_SEC)

        print(f'\nNewly filled this run: {newly_filled}')

    total_with_wx = sum(1 for r in rows if r[COL_TMIN])
    print(f'Rows with weather data: {total_with_wx}/{len(rows)} '
          f'({total_with_wx/len(rows)*100:.1f}%)')

    with open(STREAMS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    print(f'Saved {STREAMS_PATH} ({os.path.getsize(STREAMS_PATH)/1024:.1f} KB)')

    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f)
    print(f'Saved {CACHE_PATH} ({os.path.getsize(CACHE_PATH)/1024:.1f} KB)')


if __name__ == '__main__':
    main()
