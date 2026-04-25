# Run this script whenever the Google Sheet data is updated to refresh the
# local data cache used by Analytics.html.
#
#   python update_data.py
#
# Output: assets/data/streams.json
# After running, commit the updated streams.json to the repo and push.

import urllib.request
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

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'data', 'streams.json')


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


def main():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    source = fetch_csv(SOURCE_URL, 'stream data')
    campsites = fetch_csv(CAMPSITE_URL, 'campsite data')
    stream_info = fetch_csv(STREAM_INFO_URL, 'stream info')

    output = {'source': source, 'campsites': campsites, 'stream_info': stream_info}

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f'Saved to {OUTPUT_PATH} ({size_kb:.1f} KB)')


if __name__ == '__main__':
    main()
