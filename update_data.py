# Run this script whenever the Google Sheet data is updated to refresh the
# local data cache used by Analytics.html.
#
#   python update_data.py
#
# Output: assets/data/streams.json
# After running, commit the updated streams.json to the repo and push.
#
# If weather_cache.json exists (created by fill_weather.py), it is
# automatically merged in so filled weather data survives sheet re-downloads.

import urllib.request
import urllib.parse
import csv
import json
import os
import io

SHEET_ID = '2PACX-1vRDZny6ZfKGXJOKIgoRo47knNJmmtDT2WTrNvOmQ0lwUiznaF1McQVgpTUa1kTMUpq5X6c3b888BGwz'
SOURCE_GID = '491893533'
CAMPSITE_GID = '212109608'
STREAM_INFO_GID = '1772368131'

SOURCE_URL = f'https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pub?gid={SOURCE_GID}&single=true&output=csv'
CAMPSITE_URL = f'https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pub?gid={CAMPSITE_GID}&single=true&output=csv'
STREAM_INFO_URL = f'https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pub?gid={STREAM_INFO_GID}&single=true&output=csv'

OUTPUT_PATH     = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'streams.json')
CACHE_PATH      = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'weather_cache.json')
DNR_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'dnr_streams.geojson')

DNR_QUERY_URL = (
    'https://dnrmaps.wi.gov/arcgis/rest/services/FM_Trout/'
    'FM_TROUT_REGS_WTM_Ext/MapServer/0/query'
)

FIELD_MAP = [
    (21, 'tmin'), (22, 'tmax'), (23, 'condition'), (24, 'precip'),
    (25, 'recent_rain'), (26, 'wind_speed'), (27, 'wind_dir'),
    (28, 'pressure'), (29, 'pressure_trend'),
]


def fetch_csv(url, label):
    print(f'Fetching {label}...')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode('utf-8')
    except Exception as e:
        print(f'  ERROR fetching {label}: {e}')
        raise

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        raise ValueError(f'{label} returned empty data')

    headers = rows[0]
    data = rows[1:]
    print(f'  {len(data)} rows, {len(headers)} columns')
    return {'headers': headers, 'rows': data}


def _cache_key(date_mdy, lat_s, lon_s):
    try:
        p = date_mdy.strip().split('/')
        iso = f"{p[2]}-{int(p[0]):02d}-{int(p[1]):02d}"
        return f"{iso}_{round(float(lat_s), 2):.2f}_{round(float(lon_s), 2):.2f}"
    except Exception:
        return None


def apply_weather_cache(rows):
    if not os.path.exists(CACHE_PATH):
        return 0
    with open(CACHE_PATH, encoding='utf-8') as f:
        cache = json.load(f)
    applied = 0
    for row in rows:
        if row[21]:  # already has min temp — sheet data takes priority
            continue
        key = _cache_key(row[0], row[12], row[13])
        if not key or key not in cache:
            continue
        wx = cache[key]
        for col, field in FIELD_MAP:
            if not row[col] and wx.get(field):
                row[col] = wx[field]
        applied += 1
    return applied


def fetch_dnr_regulations(source_rows):
    """Fetch DNR regulation attributes (no geometry) and match to user stream names."""
    import re
    print('Fetching WI DNR regulation details (attributes only)...')
    all_attrs = []
    offset = 0
    page_size = 1000

    while True:
        params = urllib.parse.urlencode({
            'where': '1=1',
            'outFields': 'STREAM,REGCAT,BAG_LMT,SEASON_TXT,EARLY_SEASON_TXT,GEAR_RESTRICTIONS,SPECIALREG1',
            'returnGeometry': 'false',
            'f': 'json',
            'resultOffset': offset,
            'resultRecordCount': page_size,
        })
        url = f'{DNR_QUERY_URL}?{params}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f'  ERROR at offset {offset}: {e}')
            break

        features = data.get('features', [])
        all_attrs.extend(a['attributes'] for a in features)
        if len(features) < page_size:
            break
        offset += page_size

    print(f'  Downloaded {len(all_attrs)} regulation records')

    # Build DNR lookup: DNR stream name -> most common regulation entry
    dnr_by_name = {}
    fields = ['REGCAT', 'BAG_LMT', 'SEASON_TXT', 'EARLY_SEASON_TXT', 'GEAR_RESTRICTIONS', 'SPECIALREG1']
    for a in all_attrs:
        name = (a.get('STREAM') or '').strip()
        rc = (a.get('REGCAT') or '').strip()
        if not name or not rc:
            continue
        if name not in dnr_by_name:
            dnr_by_name[name] = {}
        if rc not in dnr_by_name[name]:
            dnr_by_name[name][rc] = {f: (a.get(f) or '').strip() for f in fields}
            dnr_by_name[name][rc]['_count'] = 0
        dnr_by_name[name][rc]['_count'] += 1

    # Build lookup with lowercase keys for case-insensitive matching
    dnr_lookup = {}
    for dnr_name, regcats in dnr_by_name.items():
        best = max(regcats.values(), key=lambda x: x['_count'])
        dnr_lookup[dnr_name.lower().strip()] = {f: best[f] for f in fields}

    # Match user stream names -> DNR entries
    qualifier_re = re.compile(
        r'\b(big|little|small|upper|lower|north|south|east|west|main|branch|trib|tributary)\b',
        re.IGNORECASE,
    )
    user_names = list({(row[2] or '').strip() for row in source_rows if (row[2] or '').strip()})
    result = {}
    for user_name in user_names:
        key = qualifier_re.sub('', user_name).strip().lower()
        key = ' '.join(key.split())
        if not key:
            continue
        if key in dnr_lookup:
            result[user_name] = dnr_lookup[key]
            continue
        words = key.split()
        matches = [(n, d) for n, d in dnr_lookup.items() if all(w in n for w in words)]
        if matches:
            matches.sort(key=lambda x: len(x[0]))
            result[user_name] = matches[0][1]

    print(f'  Matched {len(result)} of {len(user_names)} user streams to DNR data')
    return result


def fetch_dnr_streams():
    print('Fetching WI DNR classified trout stream regulations...')
    all_features = []
    offset = 0
    page_size = 1000

    while True:
        params = urllib.parse.urlencode({
            'where': '1=1',
            'outFields': 'STREAM,REGCAT,BAG_LMT',
            'outSR': '4326',
            'geometryPrecision': 4,        # 4 decimal places (~11 m)
            'maxAllowableOffset': 0.0003,  # simplify ~33 m, fine for map display
            'f': 'geojson',
            'resultOffset': offset,
            'resultRecordCount': page_size,
        })
        url = f'{DNR_QUERY_URL}?{params}'
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f'  ERROR at offset {offset}: {e}')
            break

        features = data.get('features', [])
        all_features.extend(features)
        print(f'  Page {offset // page_size + 1}: {len(features)} features (total: {len(all_features)})')

        if len(features) < page_size:
            break
        offset += page_size

    # Round coordinates to 5 decimal places (~1 m accuracy) to shrink file size
    for feat in all_features:
        geom = feat.get('geometry') or {}
        coords = geom.get('coordinates')
        if not coords:
            continue
        t = geom.get('type', '')
        if t == 'LineString':
            geom['coordinates'] = [[round(x, 5), round(y, 5)] for x, y in coords]
        elif t == 'MultiLineString':
            geom['coordinates'] = [
                [[round(x, 5), round(y, 5)] for x, y in ring]
                for ring in coords
            ]

    geojson = {'type': 'FeatureCollection', 'features': all_features}
    with open(DNR_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, separators=(',', ':'))

    size_kb = os.path.getsize(DNR_OUTPUT_PATH) / 1024
    print(f'  Saved {len(all_features)} stream segments to dnr_streams.geojson ({size_kb:.0f} KB)')


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    source = fetch_csv(SOURCE_URL, 'stream data')
    campsites = fetch_csv(CAMPSITE_URL, 'campsite data')
    stream_info = fetch_csv(STREAM_INFO_URL, 'stream info')

    output = {'source': source, 'campsites': campsites, 'stream_info': stream_info}

    applied = apply_weather_cache(output['source']['rows'])
    if applied:
        print(f'Applied weather cache to {applied} rows')

    dnr_regulations = fetch_dnr_regulations(source['rows'])
    output['dnr_regulations'] = dnr_regulations

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f'Saved to {OUTPUT_PATH} ({size_kb:.1f} KB)')

    fetch_dnr_streams()


if __name__ == '__main__':
    main()
