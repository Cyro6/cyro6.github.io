"""
Enriches dnr_streams.geojson with computed Strahler stream order and arbolate sum
by building a directed network from NHD flowline geometry and computing order
via topological traversal.

Matching strategy:
  1. Name-based: match DNR STREAM name → NHD GNIS_Name (case-insensitive).
     Among name-matched NHD segments, pick nearest to the DNR arc midpoint.
  2. Fallback: nearest NHD segment to arc midpoint (for unnamed tributaries).

Using the arc midpoint (interpolate at 0.5) rather than bounding-box centroid
avoids the confluence problem where a tributary's centroid lands close to the
main stem's high-arbolate NHD segments.
"""

import json
from collections import defaultdict, deque
import geopandas as gpd
from shapely.geometry import shape
from shapely.strtree import STRtree
import numpy as np

GPKG    = 'NHD_H_Wisconsin_State_GPKG.gpkg'
DNR_IN  = 'assets/data/dnr_streams.geojson'
DNR_OUT = 'assets/data/dnr_streams.geojson'

SNAP = 6  # decimal degrees ≈ 0.1m — catches identical coords at junctions

def snap(x, y):
    return (round(x, SNAP), round(y, SNAP))

def geom_endpoints(geom):
    """Return (start_pt, end_pt) as (x,y) tuples. NHD is digitized upstream→downstream."""
    if geom.geom_type == 'LineString':
        coords = list(geom.coords)
        return snap(*coords[0][:2]), snap(*coords[-1][:2])
    elif geom.geom_type == 'MultiLineString':
        parts = list(geom.geoms)
        return snap(*list(parts[0].coords)[0][:2]), snap(*list(parts[-1].coords)[-1][:2])
    return None, None

def arc_midpoint(geom):
    """Return the point at 50% of arc length — more accurate than bounding-box centroid."""
    try:
        return geom.interpolate(0.5, normalized=True)
    except Exception:
        return geom.centroid

# ── 1. Load NHD StreamRiver flowlines + GNIS name ────────────────────────────
print('Loading NHD flowlines...')
fl_raw = gpd.read_file(GPKG, layer='NHDFlowline')
mask = (
    fl_raw['ftype'].astype(str).str.contains('460|StreamRiver', na=False) |
    (fl_raw['fcode'].astype(int) // 1000 == 46)
)
fl = fl_raw[mask][['permanent_identifier', 'gnis_name', 'geometry']].copy()
fl = fl.to_crs('EPSG:4326')
fl = fl[fl.geometry.notna()].reset_index(drop=True)
print(f'  {len(fl)} stream/river flowlines')

# ── 2. Build directed network ─────────────────────────────────────────────────
print('Building directed network...')
starts_map = {}
ends_map   = {}
incoming   = defaultdict(list)
outgoing   = defaultdict(list)
seg_len_km = {}

for _, row in fl.iterrows():
    pid  = row['permanent_identifier']
    geom = row.geometry
    s, e = geom_endpoints(geom)
    if s is None:
        continue
    starts_map[pid] = s
    ends_map[pid]   = e
    incoming[e].append(pid)
    outgoing[s].append(pid)
    try:
        seg_len_km[pid] = geom.length * 111.0
    except Exception:
        seg_len_km[pid] = 0.0

all_pids = list(starts_map.keys())
print(f'  {len(all_pids)} flowlines in network')

# ── 3. Compute Strahler order + arbolate sum via topological sort ─────────────
print('Computing Strahler order...')

def predecessors(pid):
    return incoming.get(starts_map[pid], [])

unresolved = {pid: len(predecessors(pid)) for pid in all_pids}
queue = deque(pid for pid, cnt in unresolved.items() if cnt == 0)
strahler  = {}
arb_sum   = {}
processed = 0

while queue:
    pid   = queue.popleft()
    preds = predecessors(pid)
    pred_orders = [strahler[p] for p in preds]

    if not pred_orders:
        strahler[pid] = 1
        arb_sum[pid]  = seg_len_km.get(pid, 0.0)
    else:
        max_o = max(pred_orders)
        strahler[pid] = max_o + 1 if pred_orders.count(max_o) >= 2 else max_o
        arb_sum[pid]  = sum(arb_sum[p] for p in preds) + seg_len_km.get(pid, 0.0)

    processed += 1
    for succ in outgoing.get(ends_map[pid], []):
        if succ in unresolved:
            unresolved[succ] -= 1
            if unresolved[succ] == 0:
                queue.append(succ)

for pid in all_pids:
    if pid not in strahler:
        strahler[pid] = 1
        arb_sum[pid]  = seg_len_km.get(pid, 0.0)

print(f'  Processed: {processed}/{len(all_pids)}')
print(f'  Order range: {min(strahler.values())} – {max(strahler.values())}')
print(f'  Arbolate sum range: {min(arb_sum.values()):.1f} – {max(arb_sum.values()):.1f} km')

# ── 4. Build spatial index + name index ──────────────────────────────────────
print('Building spatial index and name index...')
fl_indexed = fl.set_index('permanent_identifier')
pid_array  = np.array(all_pids)
geom_array = fl_indexed.loc[pid_array, 'geometry'].values
tree       = STRtree(geom_array)

# Name index: normalized GNIS name → list of (pid, arc_midpoint)
# Used to constrain spatial search to same-named NHD segments first.
name_index = defaultdict(list)  # lower_name → [(pid, midpt)]
for pid in all_pids:
    raw_name = fl_indexed.loc[pid, 'gnis_name']
    name = str(raw_name).strip().lower() if raw_name and str(raw_name) != 'nan' else ''
    if name:
        midpt = arc_midpoint(fl_indexed.loc[pid, 'geometry'])
        name_index[name].append((pid, midpt))

named_count = sum(len(v) for v in name_index.values())
print(f'  {len(name_index)} distinct NHD stream names ({named_count} segments indexed by name)')

# ── 5. Load DNR streams and match ─────────────────────────────────────────────
print('Loading DNR streams...')
with open(DNR_IN) as f:
    dnr = json.load(f)
print(f'  {len(dnr["features"])} DNR features')

name_matched = 0
fallback_matched = 0

for feat in dnr['features']:
    try:
        geom     = shape(feat['geometry'])
        midpt    = arc_midpoint(geom)
        dnr_name = str(feat['properties'].get('STREAM') or '').strip().lower()

        pid = None

        # ── Strategy 1: name-based match ──────────────────────────────────────
        candidates = name_index.get(dnr_name)
        if candidates:
            best_d = float('inf')
            for c_pid, c_midpt in candidates:
                d = midpt.distance(c_midpt)
                if d < best_d:
                    best_d = d
                    pid = c_pid
            name_matched += 1

        # ── Strategy 2: global nearest-neighbor fallback ──────────────────────
        if pid is None:
            idx = tree.nearest(midpt)
            pid = pid_array[idx]
            fallback_matched += 1

        feat['properties']['stream_order']    = int(strahler[pid])
        feat['properties']['arbolate_sum_km'] = round(float(arb_sum[pid]), 2)
    except Exception as e:
        feat['properties']['stream_order']    = None
        feat['properties']['arbolate_sum_km'] = None

total = name_matched + fallback_matched
print(f'  Name-matched: {name_matched}/{total}  |  Fallback: {fallback_matched}/{total}')

# ── 6. Write output ───────────────────────────────────────────────────────────
print('Writing enriched GeoJSON...')
with open(DNR_OUT, 'w') as f:
    json.dump(dnr, f, separators=(',', ':'))
print('Done.')

from collections import Counter
orders = [feat['properties'].get('stream_order')
          for feat in dnr['features']
          if feat['properties'].get('stream_order')]
dist = Counter(orders)
print('Stream order distribution:')
for k in sorted(dist):
    print(f'  Order {k}: {dist[k]} segments')
