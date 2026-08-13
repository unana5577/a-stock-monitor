"""4指数天时回测 — 读缓存 + online_debug_data"""
import json, os
from datetime import date
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 4个指数 ──
INDICES = {
    "sh000001": "上证指数", "sz399001": "深证成指",
    "sz399006": "创业板指", "sh000688": "科创50",
}

TIANGAN_WUXING = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土","己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}
PHASE_NAMES = ["新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"]

# ── 加载天时缓存 ──
cache = {}
with open(os.path.join(ROOT, "data", "astro", "astro_calendar.jsonl")) as f:
    for line in f:
        r = json.loads(line.strip())
        cache[r["date"]] = r

# ── 加载指数日线 ──
def load_index(code):
    fp = os.path.join(ROOT, "online_debug_data", "index", f"{code}_daily.jsonl")
    recs = {}
    if os.path.exists(fp):
        for line in open(fp):
            r = json.loads(line.strip() or "{}")
            d = r.get("date", "")
            if d:
                recs[d] = {
                    "pct": round(float(r.get("pct", 0) or 0), 4),
                    "close": float(r.get("close", 0) or 0),
                }
    return recs

idx_data = {code: load_index(code) for code in INDICES}

# ── 交易日列表 ──
all_dates = sorted(set().union(*[recs.keys() for recs in idx_data.values()]))

def stat(arr):
    if not arr: return {"count":0,"avg":0,"winRate":0,"max":0,"min":0}
    n = len(arr); avg = sum(arr)/n
    return {"count":n,"avg":round(avg,4),"winRate":round(sum(1 for v in arr if v>0)/n,4),
            "max":round(max(arr),4),"min":round(min(arr),4)}

def cjk_pad(s, w=6):
    return s + " " * max(0, w + 6 - sum(2 if ord(c)>127 else 1 for c in s))

# ═══════════════════════════════════════════════════════
# PART 0: 对账基准 — 验证脚本准确性
# ═══════════════════════════════════════════════════════
print("=" * 80)
print("PART 0: 对账基准 — 验证脚本准确性")
print("=" * 80)

benchmarks = [
    ("2026-04-02", "丙午日满月十五", {"sh000001": -0.74, "sz399001": -1.60, "sz399006": -2.31, "sh000688": -2.77}),
    ("2026-04-01", "乙巳日满月十四", {"sh000001": 1.46, "sz399001": 1.70, "sz399006": 1.96, "sh000688": 3.33}),
]

for day, desc, expected in benchmarks:
    astro = cache.get(day, {})
    ok = True
    parts = []
    for code, name in INDICES.items():
        actual = idx_data[code].get(day, {}).get("pct")
        exp = expected.get(code)
        match = "✓" if actual is not None and abs(actual - exp) < 0.1 else "✗"
        if match == "✗": ok = False
        parts.append(f"{name}={actual:+.2f}%({match})")
    tag = "✅ 对账通过" if ok else "❌ 对账失败"
    print(f"  {day} {desc}: {' | '.join(parts)}  {tag}")

# ═══════════════════════════════════════════════════════
# PART 1: 月相节点 × 4指数
# ═══════════════════════════════════════════════════════
print()
print("=" * 80)
print("PART 1: 月相节点 × 4指数")
print("=" * 80)

phase_pct = {pi: {c: [] for c in INDICES} for pi in range(8)}
phase_dates = {pi: [] for pi in range(8)}

for td in all_dates:
    a = cache.get(td, {})
    pi = a.get("phaseIdx", -1)
    if pi < 0: continue
    phase_dates[pi].append(td)
    for code in INDICES:
        r = idx_data[code].get(td)
        if r: phase_pct[pi][code].append(r["pct"])

# 满月日列表 + 新月日列表
fm_dates = sorted(phase_dates[4])
nm_dates = sorted(phase_dates[0])
print(f"满月日 ({len(fm_dates)}次): {', '.join(fm_dates[:8])}...")
print(f"新月日 ({len(nm_dates)}次): {', '.join(nm_dates[:8])}...")
print()

for pi in range(8):
    pname = PHASE_NAMES[pi]
    print(f"  【{pname}】 {len(phase_dates[pi])}次")
    for code, name in INDICES.items():
        s = stat(phase_pct[pi][code])
        bar = "+" if s["avg"] >= 0 else ""
        print(f"    {cjk_pad(name)} avg {bar}{s['avg']:.2f}%  win {s['winRate']:.0%}  n={s['count']}  max={s['max']:.2f}%  min={s['min']:.2f}%")

# 月相转折
print()
print("--- 残月→新月 (月缺反弹) ---")
trans_pct = {c: [] for c in INDICES}
for i, td in enumerate(all_dates[:-1]):
    a_cur = cache.get(td, {}); a_nxt = cache.get(all_dates[i+1], {})
    if a_cur.get("phaseIdx") == 7 and a_nxt.get("phaseIdx") == 0:  # 残月→新月
        for code in INDICES:
            r = idx_data[code].get(all_dates[i+1])
            if r: trans_pct[code].append(r["pct"])
for code, name in INDICES.items():
    s = stat(trans_pct[code])
    print(f"  {cjk_pad(name)} avg {s['avg']:+.2f}%  win {s['winRate']:.0%}  n={s['count']}")

print()
print("--- 满月→亏凸月 (月满则亏) ---")
trans_pct2 = {c: [] for c in INDICES}
for i, td in enumerate(all_dates[:-1]):
    a_cur = cache.get(td, {}); a_nxt = cache.get(all_dates[i+1], {})
    if a_cur.get("phaseIdx") == 4 and a_nxt.get("phaseIdx") == 5:
        for code in INDICES:
            r = idx_data[code].get(all_dates[i+1])
            if r: trans_pct2[code].append(r["pct"])
for code, name in INDICES.items():
    s = stat(trans_pct2[code])
    print(f"  {cjk_pad(name)} avg {s['avg']:+.2f}%  win {s['winRate']:.0%}  n={s['count']}")

# ═══════════════════════════════════════════════════════
# PART 2: 天干 × 4指数
# ═══════════════════════════════════════════════════════
print()
print("=" * 80)
print("PART 2: 10天干日 × 4指数")
print("=" * 80)

tg_idx = {code: defaultdict(list) for code in INDICES}
for td in all_dates:
    a = cache.get(td, {}); tg = a.get("tg", "")
    if not tg: continue
    for code in INDICES:
        r = idx_data[code].get(td)
        if r: tg_idx[code][tg].append(r["pct"])

TIANGAN = ["甲","乙","丙","丁","戊","己","庚","辛","壬","癸"]
print(f"\n  {'日干':<6s}", end="")
for code, name in INDICES.items():
    print(f"  {name:>10s}", end="")
print(f"\n  {'-'*6}", end="")
for _ in INDICES: print(f"  {'-'*10}", end="")
print()
for tg in TIANGAN:
    print(f"  {tg}({TIANGAN_WUXING.get(tg,'?')}) ", end="")
    for code in INDICES:
        s = stat(tg_idx[code].get(tg, []))
        bar = "+" if s["avg"] >= 0 else ""
        print(f"  {bar}{s['avg']:>8.2f}%", end="")
    print()

# 每指数最佳/最差天干
print()
for code, name in INDICES.items():
    ranked = sorted(
        [(tg, stat(tg_idx[code].get(tg, []))) for tg in TIANGAN if tg_idx[code].get(tg)],
        key=lambda x: -x[1]["avg"]
    )
    best3 = ranked[:3]
    worst3 = sorted(ranked, key=lambda x: x[1]["avg"])[:3]
    print(f"  {name}: 最佳→{', '.join(f'{t}({TIANGAN_WUXING.get(t,'?')})+{v['avg']:.2f}%' for t,v in best3)}  "
          f"最差→{', '.join(f'{t}({TIANGAN_WUXING.get(t,'?')}){v['avg']:.2f}%' for t,v in worst3)}")

# ═══════════════════════════════════════════════════════
# PART 3: 流月 × 4指数
# ═══════════════════════════════════════════════════════
print()
print("=" * 80)
print("PART 3: 流月干支 × 4指数")
print("=" * 80)

month_idx = defaultdict(lambda: {c: [] for c in INDICES})
month_dates = defaultdict(list)
for td in all_dates:
    a = cache.get(td, {}); mgz = a.get("gzMonth", "")
    if not mgz: continue
    month_dates[mgz].append(td)
    for code in INDICES:
        r = idx_data[code].get(td)
        if r: month_idx[mgz][code].append(r["pct"])

# 按出现顺序排列
seen = set(); month_order = []
for td in sorted(all_dates):
    mgz = cache.get(td, {}).get("gzMonth", "")
    if mgz and mgz not in seen:
        seen.add(mgz); month_order.append(mgz)

print()
for mgz in month_order:
    mtg = mgz[0] if mgz else ""; mdz = mgz[1] if len(mgz)>1 else ""
    print(f"  【{mgz}】月干{mtg}({TIANGAN_WUXING.get(mtg,'?')}) 月支{mdz} | {len(month_dates[mgz])}个交易日")
    best = None; worst = None
    best_v = -999; worst_v = 999
    for code, name in INDICES.items():
        s = stat(month_idx[mgz][code])
        bar = "+" if s["avg"] >= 0 else ""
        print(f"    {cjk_pad(name)} avg {bar}{s['avg']:.2f}%  win {s['winRate']:.0%}  n={s['count']}")
        if s["avg"] > best_v: best_v, best = s["avg"], name
        if s["avg"] < worst_v: worst_v, worst = s["avg"], name
    print(f"    → 本月最强:{best}({best_v:+.2f}%) 最弱:{worst}({worst_v:+.2f}%)\n")

# ═══════════════════════════════════════════════════════
# PART 4: 日干 × 流月 交互(2026年丙午年)
# ═══════════════════════════════════════════════════════
print("=" * 80)
print("PART 4: 2026年(丙午) 日干×月干交互 × 4指数")
print("=" * 80)

inter = {code: defaultdict(list) for code in INDICES}
for td in all_dates:
    a = cache.get(td, {})
    tg = a.get("tg", ""); mtg = a.get("mtg", "")
    if not tg or not mtg or td[:4] != "2026": continue
    for code in INDICES:
        r = idx_data[code].get(td)
        if r: inter[code][f"{mtg}×{tg}"].append(r["pct"])

for code, name in INDICES.items():
    significant = [(k, stat(v)) for k, v in inter[code].items() if len(v) >= 2 and abs(stat(v)["avg"]) >= 1.0]
    significant.sort(key=lambda x: -x[1]["avg"])
    if significant:
        print(f"\n  {name} 显著交互 (|avg|>=1%):")
        for k, v in significant[:6]:
            mtg = k[0]; tg = k[2]
            mwx = TIANGAN_WUXING.get(mtg, "?"); twx = TIANGAN_WUXING.get(tg, "?")
            print(f"    月{mtg}({mwx})×日{tg}({twx}): avg {v['avg']:+.2f}%  n={v['count']}")

print(f"\n数据范围: {all_dates[0]} ~ {all_dates[-1]} ({len(all_dates)}个交易日)")
