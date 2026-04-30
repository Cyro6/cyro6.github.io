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


EXCLUDED_STREAMS = {'Unknown', 'Central Sands', 'Minnesota', 'Southern WI'}

REG_FIELDS = ['REGCAT', 'BAG_LMT', 'SEASON_TXT', 'EARLY_SEASON_TXT', 'GEAR_RESTRICTIONS', 'SPECIALREG1']


def fetch_dnr_attributes():
    """Fetch DNR regulation attributes (no geometry).
    Returns: {dnr_stream_name_lowercase: {REGCAT, BAG_LMT, SEASON_TXT, ...}}
    """
    print('Fetching WI DNR regulation attributes...')
    all_attrs = []
    offset = 0
    page_size = 1000

    while True:
        params = urllib.parse.urlencode({
            'where': '1=1',
            'outFields': ','.join(['STREAM'] + REG_FIELDS),
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

    # Build lookup keyed by lowercase DNR stream name; pick most common REGCAT per name
    by_name = {}
    for a in all_attrs:
        name = (a.get('STREAM') or '').strip().lower()
        rc   = (a.get('REGCAT') or '').strip()
        if not name or not rc:
            continue
        by_name.setdefault(name, {})
        if rc not in by_name[name]:
            by_name[name][rc] = {f: (a.get(f) or '').strip() for f in REG_FIELDS}
            by_name[name][rc]['_cnt'] = 0
        by_name[name][rc]['_cnt'] += 1

    lookup = {}
    for dnr_name, regcats in by_name.items():
        best = max(regcats.values(), key=lambda x: x['_cnt'])
        lookup[dnr_name] = {f: best[f] for f in REG_FIELDS}

    print(f'  {len(all_attrs)} records, {len(lookup)} unique DNR streams')
    return lookup


def build_dnr_lookup_by_gps(source_rows, dnr_attr_lookup):
    """Match user stream names to DNR regulations using GPS proximity.
    Uses the already-saved dnr_streams.geojson for geometry and
    dnr_attr_lookup (from fetch_dnr_attributes) for full detail fields.
    Returns: {user_stream_name: {REGCAT, BAG_LMT, SEASON_TXT, ...}}
    """
    MAX_DSQ = 0.02 ** 2  # ~2 km threshold in degrees-squared

    print('Matching user streams to DNR regulations by GPS proximity...')

    with open(DNR_OUTPUT_PATH, encoding='utf-8') as f:
        gj = json.load(f)

    # Pre-process geometry into flat list of (dnr_name_lower, [(ax,ay,bx,by),...])
    dnr_segs = []
    for feat in gj['features']:
        name  = (feat['properties'].get('STREAM') or '').strip().lower()
        geom  = feat.get('geometry') or {}
        gt    = geom.get('type', '')
        coords = geom.get('coordinates', [])
        lines  = [coords] if gt == 'LineString' else (coords if gt == 'MultiLineString' else [])
        segs = [
            (line[i][0], line[i][1], line[i+1][0], line[i+1][1])
            for line in lines
            for i in range(len(line) - 1)
        ]
        if segs:
            dnr_segs.append((name, segs))

    def pt_seg_dsq(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return (px - ax) ** 2 + (py - ay) ** 2
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2

    def nearest_dnr(lon, lat):
        best_dsq, best_name = float('inf'), None
        for name, segs in dnr_segs:
            for ax, ay, bx, by in segs:
                d = pt_seg_dsq(lon, lat, ax, ay, bx, by)
                if d < best_dsq:
                    best_dsq, best_name = d, name
        return best_name, best_dsq

    # Collect GPS points per user stream (GeoJSON order: lon, lat)
    stream_gps = {}
    for row in source_rows:
        name = (row[2] or '').strip()
        if not name or name in EXCLUDED_STREAMS:
            continue
        try:
            lat = float(row[12])
            lon = float(row[13])
        except (ValueError, IndexError):
            continue
        if abs(lat) < 0.001 or abs(lon) < 0.001:
            continue
        stream_gps.setdefault(name, []).append((lon, lat))

    # Vote: for each GPS point find nearest DNR segment; most votes wins
    result = {}
    for user_name, points in stream_gps.items():
        votes = {}
        for lon, lat in points:
            dnr_name, dsq = nearest_dnr(lon, lat)
            if dnr_name and dsq < MAX_DSQ:
                votes[dnr_name] = votes.get(dnr_name, 0) + 1
        if votes:
            best = max(votes, key=votes.get)
            attrs = dnr_attr_lookup.get(best)
            if attrs:
                result[user_name] = attrs
                print(f'    {user_name!r:35s} -> {best!r}')

    print(f'  GPS-matched {len(result)} of {len(stream_gps)} streams')
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

    fetch_dnr_streams()
    dnr_attrs = fetch_dnr_attributes()
    dnr_regulations = build_dnr_lookup_by_gps(source['rows'], dnr_attrs)
    output['dnr_regulations'] = dnr_regulations

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f'Saved to {OUTPUT_PATH} ({size_kb:.1f} KB)')


if __name__ == '__main__':
    main()
