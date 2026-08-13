import json
from datetime import datetime

path = '/Users/una5577/Documents/trae_projects/a-stock-monitor/data/sector-proxy.json'
with open(path) as f:
    d = json.load(f)

# Remove wrong entries
removed = []
for bad_key in ['sh159995', 'sh159157']:
    if bad_key in d['variants']['etf']:
        removed.append(bad_key)
        del d['variants']['etf'][bad_key]
    if bad_key in d['etf_meta']:
        del d['etf_meta'][bad_key]

d['updated_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

with open(path, 'w') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

etfs = d['variants']['etf']
print(f'Removed: {removed}')
print(f'Remaining: {len(etfs)} ETFs')
for name, code in etfs.items():
    print(f'  {code:14s} {name}')
