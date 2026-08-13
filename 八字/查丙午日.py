import json, os
from datetime import date, timedelta
from tyme4py.solar import SolarDay

ROOT = '/Users/una5577/Documents/trae_projects/a-stock-monitor'
INDICES = {'sh000001':'上证','sz399001':'深证','sz399006':'创业','sh000688':'科创'}

records = {}
for code in INDICES:
    fp = os.path.join(ROOT, 'data', 'index', 'daily', code, 'daily.jsonl')
    recs = {}
    with open(fp) as f:
        for line in f:
            r = json.loads(line.strip() or '{}')
            d = r.get('date','')
            if d: recs[d] = round(float(r.get('pct',0) or 0), 2)
    records[code] = recs

start = date(2026, 1, 1)
end = date(2026, 6, 15)
cur = start
bingwu = []
while cur <= end:
    sd = SolarDay.from_ymd(cur.year, cur.month, cur.day)
    gz = sd.get_sixty_cycle_day().get_name().replace('日','')
    if gz == '丙午':
        ld = sd.get_lunar_day()
        lunar = ld.get_name() if ld else ''
        bingwu.append((cur.isoformat(), lunar))
        print(f'{cur} 丙午日 农历{lunar}')
    cur += timedelta(days=1)

print(f'\n共 {len(bingwu)} 个丙午日')
print(f'{"日期":<14s} {"周几":<5s} {"上证":>8s} {"深证":>8s} {"创业":>8s} {"科创":>8s}  涨跌')
print('-' * 62)
up = 0; dn = 0
for d, lunar in bingwu:
    dt = date.fromisoformat(d)
    wd = ['一','二','三','四','五','六','日'][dt.weekday()]
    sh = records['sh000001'].get(d)
    sz = records['sz399001'].get(d)
    cy = records['sz399006'].get(d)
    kc = records['sh000688'].get(d)
    if sh is None:
        print(f'{d:<14s} 周{wd:<4s} {"休市":>8s}')
        continue
    up_all = all(v > 0 for v in [sh,sz,cy,kc] if v is not None)
    dn_all = all(v < 0 for v in [sh,sz,cy,kc] if v is not None)
    tag = '全涨' if up_all else ('全跌' if dn_all else '分化')
    if up_all: up += 1
    if dn_all: dn += 1
    print(f'{d:<14s} 周{wd:<4s} {sh:>+7.2f}% {sz:>+7.2f}% {cy:>+7.2f}% {kc:>+7.2f}%  {tag}')

print(f'\n全涨{up}次 全跌{dn}次 / {len(bingwu)}天')
