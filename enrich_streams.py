"""
Enriches dnr_streams.geojson with computed Strahler stream order and arbolate sum
by building a directed network from NHD flowline geometry and computing order
via topological traversal. NHD linestrings are digitized upstream→downstream,
so coords[0] = upstream end and coords[-1] = downstream end.
"""

import json
from collections import defaultdict, deque
import geopandas as gpd
from shapely.geometry import shape, Point
from shapely.strtree import STRtree
import numpy as np

GPKG    = 'NHD_H_Wisconsin_State_GPKG.gpkg'
DNR_IN  = 'assets/data/dnr_streams.geojson'
DNR_OUT = 'assets/data/dnr_streams.geojson'

# Snap precision: 6 decimal degrees ≈ 0.1m — catches identical coords at junctions
SNAP = 6

def snap(x, y):
    return (round(x, SNAP), round(y, SNAP))

def geom_endpoints(geom):
    """Return (start_pt, end_pt) as (x,y) tuples from a LineString or MultiLineString."""
    if geom.geom_type == 'LineString':
        coords = list(geom.coords)
        return snap(*coords[0][:2]), snap(*coords[-1][:2])
    elif geom.geom_type == 'MultiLineString':
        parts = list(geom.geoms)
        start = list(parts[0].coords)[0]
        end   = list(parts[-1].coords)[-1]
        return snap(*start[:2]), snap(*end[:2])
    return None, None

# ── 1. Load NHD StreamRiver flowlines ───────────────────────────────────────
print('Loading NHD flowlines...')
fl = gpd.read_file(GPKG, layer='NHDFlowline')
mask = (
    fl['ftype'].astype(str).str.contains('460|StreamRiver', na=False) |
    (fl['fcode'].astype(int) // 1000 == 46)
)
fl = fl[mask][['permanent_identifier', 'geometry']].copy()
fl = fl.to_crs('EPSG:4326')
fl = fl[fl.geometry.notna()].reset_index(drop=True)
print(f'  {len(fl)} stream/river flowlines')

# ── 2. Build directed network ────────────────────────────────────────────────
print('Building directed network...')
starts_map   = {}  # pid → start_node
ends_map     = {}  # pid → end_node
incoming     = defaultdict(list)  # node → [pids that END here (flow into node)]
outgoing     = defaultdict(list)  # node → [pids that START here (flow from node)]
seg_len_km   = {}  # pid → length in km (approx from degrees * 111)

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
    # Approximate length: project to a meter-based CRS would be more accurate,
    # but for relative arbolate-sum ordering, degree-based is sufficient.
    try:
        seg_len_km[pid] = geom.length * 111.0
    except Exception:
        seg_len_km[pid] = 0.0

all_pids = list(starts_map.keys())
print(f'  {len(all_pids)} flowlines in network')

# ── 3. Compute Strahler order + arbolate sum via Kahn's topological sort ─────
print('Computing Strahler order via topological traversal...')

def predecessors(pid):
    """Edges whose downstream end feeds into pid's upstream start."""
    return incoming.get(starts_map[pid], [])

# Count how many upstream predecessors each edge is waiting on
unresolved = {pid: len(predecessors(pid)) for pid in all_pids}
queue = deque(pid for pid, cnt in unresolved.items() if cnt == 0)

strahler   = {}   # pid → int
arb_sum    = {}   # pid → float (km)
processed  = 0

while queue:
    pid = queue.popleft()
    preds = predecessors(pid)
    pred_orders = [strahler[p] for p in preds]

    if not pred_orders:
        strahler[pid] = 1
        arb_sum[pid]  = seg_len_km.get(pid, 0.0)
    else:
        max_o     = max(pred_orders)
        count_max = pred_orders.count(max_o)
        strahler[pid] = max_o + 1 if count_max >= 2 else max_o
        arb_sum[pid]  = sum(arb_sum[p] for p in preds) + seg_len_km.get(pid, 0.0)

    processed += 1

    # Unlock successors
    end_node = ends_map[pid]
    for succ in outgoing.get(end_node, []):
        if succ in unresolved:
            unresolved[succ] -= 1
            if unresolved[succ] == 0:
                queue.append(succ)

unprocessed = len(all_pids) - processed
print(f'  Processed: {processed}, Skipped (cycles/disconnected): {unprocessed}')

# Any cycles or stranded edges: fall back to order 1
for pid in all_pids:
    if pid not in strahler:
        strahler[pid] = 1
        arb_sum[pid]  = seg_len_km.get(pid, 0.0)

orders_all = list(strahler.values())
print(f'  Stream order range: {min(orders_all)} – {max(orders_all)}')
arb_all = list(arb_sum.values())
print(f'  Arbolate sum range: {min(arb_all):.1f} – {max(arb_all):.1f} km')

# ── 4. Build spatial index on NHD flowlines ──────────────────────────────────
print('Building spatial index...')
fl_indexed = fl.set_index('permanent_identifier')
pid_array  = np.array(list(starts_map.keys()))
geom_array = fl_indexed.loc[pid_array, 'geometry'].values
tree       = STRtree(geom_array)

# ── 5. Load DNR streams and match ────────────────────────────────────────────
print('Loading DNR streams...')
with open(DNR_IN) as f:
    dnr = json.load(f)

print(f'  {len(dnr["features"])} DNR features — matching to NHD...')

matched = 0
for feat in dnr['features']:
    try:
        geom = shape(feat['geometry'])
        pt   = geom.centroid
        idx  = tree.nearest(pt)
        pid  = pid_array[idx]
        feat['properties']['stream_order']    = int(strahler[pid])
        feat['properties']['arbolate_sum_km'] = round(float(arb_sum[pid]), 2)
        matched += 1
    except Exception as e:
        feat['properties']['stream_order']    = None
        feat['properties']['arbolate_sum_km'] = None

print(f'  Matched {matched}/{len(dnr["features"])} features')

# ── 6. Write output ───────────────────────────────────────────────────────────
print('Writing enriched GeoJSON...')
with open(DNR_OUT, 'w') as f:
    json.dump(dnr, f, separators=(',', ':'))
print('Done.')

from collections import Counter
orders_dist = [feat['properties'].get('stream_order')
               for feat in dnr['features']
               if feat['properties'].get('stream_order')]
dist = Counter(orders_dist)
print('Stream order distribution:')
for k in sorted(dist):
    print(f'  Order {k}: {dist[k]} segments')
