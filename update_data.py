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
import sys

SHEET_ID = '2PACX-1vRDZny6ZfKGXJOKIgoRo47knNJmmtDT2WTrNvOmQ0lwUiznaF1McQVgpTUa1kTMUpq5X6c3b888BGwz'
SOURCE_GID = '491893533'
CAMPSITE_GID = '212109608'
STREAM_INFO_GID = '1772368131'

SOURCE_URL = f'https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pub?gid={SOURCE_GID}&single=true&output=csv'
CAMPSITE_URL = f'https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pub?gid={CAMPSITE_GID}&single=true&output=csv'
STREAM_INFO_URL = f'https://docs.google.com/spreadsheets/d/e/{SHEET_ID}/pub?gid={STREAM_INFO_GID}&single=true&output=csv'

OUTPUT_PATH          = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'streams.json')
CACHE_PATH           = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'weather_cache.json')
DNR_OUTPUT_PATH      = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'dnr_streams.geojson')
MANAGED_LANDS_PATH   = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'dnr_managed_lands.geojson')
EASEMENT_STREAMS_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'dnr_easement_streams.geojson')
PARKING_PATH         = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'dnr_parking.geojson')
HABITAT_PATH         = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'dnr_habitat_projects.geojson')
BRIDGE_PATH          = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'dnr_bridge_crossings.geojson')

OVERPASS_URL = 'https://overpass-api.de/api/interpreter'

DNR_QUERY_URL = (
    'https://dnrmaps.wi.gov/arcgis/rest/services/FM_Trout/'
    'FM_TROUT_REGS_WTM_Ext/MapServer/0/query'
)
MANAGED_LANDS_URL = (
    'https://dnrmaps.wi.gov/arcgis/rest/services/LF_DML/'
    'LF_DNR_MGD_PROP_WTM_Ext/MapServer/0/query'
)
PARKING_URL = (
    'https://dnrmaps.wi.gov/arcgis/rest/services/LF_DML/'
    'LF_DNR_BOAT_BoatAccess_WTM_Ext/MapServer/6/query'
)
HABITAT_URL = (
    'https://dnrmaps.wi.gov/arcgis/rest/services/FM_Trout/'
    'FM_TROUT_HAB_SITES_WTM_Ext/MapServer/1/query'
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


def pt_seg_dsq(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2


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
    result   = {}
    name_map = {}  # user_stream_name -> matched dnr stream name (lowercase)
    for user_name, points in stream_gps.items():
        votes = {}
        for lon, lat in points:
            dnr_name, dsq = nearest_dnr(lon, lat)
            if dnr_name and dsq < MAX_DSQ:
                votes[dnr_name] = votes.get(dnr_name, 0) + 1
        if votes:
            best = max(votes, key=votes.get)
            name_map[user_name] = best
            attrs = dnr_attr_lookup.get(best)
            if attrs:
                result[user_name] = attrs
                print(f'    {user_name!r:35s} -> {best!r}')

    print(f'  GPS-matched {len(result)} of {len(stream_gps)} streams')
    return result, name_map


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


def load_stream_segs():
    """Load trout stream polyline segments for proximity filtering."""
    with open(DNR_OUTPUT_PATH, encoding='utf-8') as f:
        gj = json.load(f)
    segs = []
    for feat in gj['features']:
        geom  = feat.get('geometry') or {}
        gt    = geom.get('type', '')
        coords = geom.get('coordinates', [])
        lines  = [coords] if gt == 'LineString' else (coords if gt == 'MultiLineString' else [])
        for line in lines:
            for i in range(len(line) - 1):
                segs.append((line[i][0], line[i][1], line[i+1][0], line[i+1][1]))
    return segs


def min_stream_dsq(lon, lat, segs):
    return min((pt_seg_dsq(lon, lat, ax, ay, bx, by) for ax, ay, bx, by in segs), default=float('inf'))


def _fetch_arcgis_geojson(query_url, params_extra, label):
    """Paginate an ArcGIS REST endpoint and return all GeoJSON features."""
    all_features = []
    offset = 0
    page_size = 1000
    while True:
        params = urllib.parse.urlencode({
            'where': '1=1',
            'outSR': '4326',
            'geometryPrecision': 4,
            'f': 'geojson',
            'resultOffset': offset,
            'resultRecordCount': page_size,
            **params_extra,
        })
        url = f'{query_url}?{params}'
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
    return all_features


def fetch_dnr_managed_lands(stream_segs):
    """Download DNR managed land polygons, keep only those within ~2 km of a trout stream."""
    MAX_DSQ = 0.02 ** 2
    print('Fetching DNR managed lands...')
    features = _fetch_arcgis_geojson(MANAGED_LANDS_URL, {
        'outFields': 'PROP_NAME,ACRES,PUBLIC_ACCESS,TRANS_TYPE',
        'maxAllowableOffset': 0.001,
    }, 'managed lands')

    kept = []
    for feat in features:
        geom   = feat.get('geometry') or {}
        gt     = geom.get('type', '')
        coords = geom.get('coordinates', [])
        if gt == 'Polygon':
            ring = coords[0] if coords else []
        elif gt == 'MultiPolygon':
            ring = coords[0][0] if coords and coords[0] else []
        else:
            continue
        if not ring:
            continue
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        if min_stream_dsq(cx, cy, stream_segs) <= MAX_DSQ:
            kept.append(feat)

    geojson = {'type': 'FeatureCollection', 'features': kept}
    with open(MANAGED_LANDS_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, separators=(',', ':'))
    size_kb = os.path.getsize(MANAGED_LANDS_PATH) / 1024
    print(f'  Kept {len(kept)} of {len(features)} properties near trout streams ({size_kb:.0f} KB)')


def fetch_dnr_parking(stream_segs):
    """Download DNR parking lots, keep only those within ~1 km of a trout stream."""
    MAX_DSQ = 0.01 ** 2
    print('Fetching DNR parking lots...')
    features = _fetch_arcgis_geojson(PARKING_URL, {
        'outFields': 'PARKING_LOT_NAME,LOCATION_DESC',
    }, 'parking')

    kept = []
    for feat in features:
        geom   = feat.get('geometry') or {}
        coords = geom.get('coordinates', [])
        if not coords or len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        if min_stream_dsq(lon, lat, stream_segs) <= MAX_DSQ:
            kept.append(feat)

    geojson = {'type': 'FeatureCollection', 'features': kept}
    with open(PARKING_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, separators=(',', ':'))
    size_kb = os.path.getsize(PARKING_PATH) / 1024
    print(f'  Kept {len(kept)} of {len(features)} parking lots near trout streams ({size_kb:.0f} KB)')


def fetch_dnr_habitat_projects():
    """Download trout habitat project reaches (polylines)."""
    print('Fetching trout habitat projects...')
    features = _fetch_arcgis_geojson(HABITAT_URL, {
        'outFields': 'WATERBODYNAMECOMBINED,SITENAMECOMBINED,FISCALYEAR,PROJECTPURPOSE,TARGETSPECIES,TECHNIQUESSTRUCTURES',
        'maxAllowableOffset': 0.0003,
    }, 'habitat projects')

    geojson = {'type': 'FeatureCollection', 'features': features}
    with open(HABITAT_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, separators=(',', ':'))
    size_kb = os.path.getsize(HABITAT_PATH) / 1024
    print(f'  Saved {len(features)} habitat project reaches ({size_kb:.0f} KB)')


def point_in_polygon(px, py, ring):
    """Ray casting point-in-polygon test."""
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate([(p[0], p[1]) for p in ring]):
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > py) != (yj > py)) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def fetch_dnr_easement_streams():
    """Intersect easement polygons with DNR stream segments.
    Outputs stream segments that fall inside easement polygons as a clean line layer.
    """
    print('Computing easement stream sections...')

    with open(MANAGED_LANDS_PATH, encoding='utf-8') as f:
        lands = json.load(f)

    # Extract easement rings with bounding boxes
    easement_rings = []
    for feat in lands['features']:
        if str(feat['properties'].get('TRANS_TYPE', '')) != '2':
            continue
        geom   = feat.get('geometry') or {}
        gt     = geom.get('type', '')
        coords = geom.get('coordinates', [])
        rings  = [coords[0]] if gt == 'Polygon' else ([p[0] for p in coords] if gt == 'MultiPolygon' else [])
        for ring in rings:
            if not ring:
                continue
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            easement_rings.append((ring, min(xs), min(ys), max(xs), max(ys)))

    print(f'  {len(easement_rings)} easement rings')

    with open(DNR_OUTPUT_PATH, encoding='utf-8') as f:
        gj = json.load(f)

    seen = set()
    out_features = []

    for feat in gj['features']:
        geom   = feat.get('geometry') or {}
        gt     = geom.get('type', '')
        coords = geom.get('coordinates', [])
        lines  = [coords] if gt == 'LineString' else (coords if gt == 'MultiLineString' else [])

        for line in lines:
            for i in range(len(line) - 1):
                ax, ay = line[i][0],   line[i][1]
                bx, by = line[i+1][0], line[i+1][1]
                key    = (ax, ay, bx, by)
                if key in seen:
                    continue

                mx, my     = (ax + bx) / 2, (ay + by) / 2
                seg_minx   = min(ax, bx)
                seg_maxx   = max(ax, bx)
                seg_miny   = min(ay, by)
                seg_maxy   = max(ay, by)

                for ring, ex1, ey1, ex2, ey2 in easement_rings:
                    if seg_maxx < ex1 or seg_minx > ex2 or seg_maxy < ey1 or seg_miny > ey2:
                        continue
                    if (point_in_polygon(mx, my, ring) or
                            point_in_polygon(ax, ay, ring) or
                            point_in_polygon(bx, by, ring)):
                        seen.add(key)
                        out_features.append({
                            'type': 'Feature',
                            'geometry': {'type': 'LineString', 'coordinates': [[ax, ay], [bx, by]]},
                            'properties': {},
                        })
                        break

    geojson = {'type': 'FeatureCollection', 'features': out_features}
    with open(EASEMENT_STREAMS_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, separators=(',', ':'))
    size_kb = os.path.getsize(EASEMENT_STREAMS_PATH) / 1024
    print(f'  {len(out_features)} stream segments within easements ({size_kb:.0f} KB)')


def fetch_bridge_crossings(stream_segs):
    """Fetch road bridge crossings over classified trout streams via OpenStreetMap Overpass API."""
    MAX_DSQ = 0.001 ** 2  # ~100m proximity to stream
    print('Fetching bridge crossings from OpenStreetMap...')

    query = '[out:json][timeout:90];\nway["bridge"="yes"]["highway"](42.4,-93.0,47.1,-86.8);\nout center;'
    url = OVERPASS_URL + '?' + urllib.parse.urlencode({'data': query})
    req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0', 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        elements = json.loads(resp.read().decode('utf-8')).get('elements', [])
    print(f'  Found {len(elements)} road bridges in Wisconsin')

    features = []
    for el in elements:
        center = el.get('center')
        if not center:
            continue
        lat, lon = center['lat'], center['lon']
        if min_stream_dsq(lon, lat, stream_segs) <= MAX_DSQ:
            tags = el.get('tags', {})
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                'properties': {
                    'name': tags.get('name', ''),
                    'highway': tags.get('highway', ''),
                }
            })

    geojson = {'type': 'FeatureCollection', 'features': features}
    with open(BRIDGE_PATH, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, separators=(',', ':'))
    size_kb = os.path.getsize(BRIDGE_PATH) // 1024
    print(f'  Saved {len(features)} bridge crossings near trout streams ({size_kb} KB)')


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
    dnr_regulations, dnr_name_map = build_dnr_lookup_by_gps(source['rows'], dnr_attrs)
    output['dnr_regulations'] = dnr_regulations
    output['dnr_name_map']    = dnr_name_map

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f'Saved to {OUTPUT_PATH} ({size_kb:.1f} KB)')

    stream_segs = load_stream_segs()
    fetch_dnr_managed_lands(stream_segs)
    fetch_dnr_easement_streams()
    fetch_dnr_parking(stream_segs)
    fetch_dnr_habitat_projects()
    fetch_bridge_crossings(stream_segs)


def build_name_map_only():
    """Build dnr_name_map from local files and patch it into streams.json.
    No network calls — reads existing streams.json and dnr_streams.geojson.
    """
    print('Building DNR name map from local files...')
    with open(OUTPUT_PATH, encoding='utf-8') as f:
        data = json.load(f)
    source_rows = data['source']['rows']

    with open(DNR_OUTPUT_PATH, encoding='utf-8') as f:
        gj = json.load(f)

    MAX_DSQ = 0.02 ** 2
    dnr_segs = []
    for feat in gj['features']:
        name  = (feat['properties'].get('STREAM') or '').strip().lower()
        geom  = feat.get('geometry') or {}
        gt    = geom.get('type', '')
        coords = geom.get('coordinates', [])
        lines  = [coords] if gt == 'LineString' else (coords if gt == 'MultiLineString' else [])
        segs = [(line[i][0], line[i][1], line[i+1][0], line[i+1][1])
                for line in lines for i in range(len(line) - 1)]
        if segs:
            dnr_segs.append((name, segs))

    stream_gps = {}
    for row in source_rows:
        name = (row[2] or '').strip()
        if not name or name in EXCLUDED_STREAMS:
            continue
        try:
            lat, lon = float(row[12]), float(row[13])
        except (ValueError, IndexError):
            continue
        if abs(lat) < 0.001 or abs(lon) < 0.001:
            continue
        stream_gps.setdefault(name, []).append((lon, lat))

    name_map = {}
    for user_name, points in stream_gps.items():
        votes = {}
        for lon, lat in points:
            best_dsq, best_name = float('inf'), None
            for dnr_name, segs in dnr_segs:
                for ax, ay, bx, by in segs:
                    d = pt_seg_dsq(lon, lat, ax, ay, bx, by)
                    if d < best_dsq:
                        best_dsq, best_name = d, dnr_name
            if best_name and best_dsq < MAX_DSQ:
                votes[best_name] = votes.get(best_name, 0) + 1
        if votes:
            best = max(votes, key=votes.get)
            name_map[user_name] = best
            print(f'  {user_name!r:35s} -> {best!r}')

    data['dnr_name_map'] = name_map
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    print(f'Saved {len(name_map)} name mappings to streams.json')


if __name__ == '__main__':
    if '--bridges-only' in sys.argv:
        os.makedirs(os.path.dirname(BRIDGE_PATH), exist_ok=True)
        stream_segs = load_stream_segs()
        fetch_bridge_crossings(stream_segs)
    elif '--name-map' in sys.argv:
        build_name_map_only()
    else:
        main()
