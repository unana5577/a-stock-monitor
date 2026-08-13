"""2026年 月度能量画像 + 4指数取象 + 风险日历"""
import json, os
from datetime import date, timedelta
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INDICES = {"sh000001":"上证","sz399001":"深证","sz399006":"创业","sh000688":"科创"}
TIANGAN_WUXING = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土","己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}
DIZHI_WUXING = {"子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火","午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水"}
PHASE_NAMES = ["新月","娥眉月","上弦月","盈凸月","满月","亏凸月","下弦月","残月"]

# ── load cache ──
cache = {}
with open(os.path.join(ROOT,"data","astro","astro_calendar.jsonl")) as f:
    for line in f:
        r = json.loads(line.strip())
        cache[r["date"]] = r

# ── load index data ──
idx_data = {}
for code in INDICES:
    fp = os.path.join(ROOT,"online_debug_data","index",f"{code}_daily.jsonl")
    recs = {}
    with open(fp) as f:
        for line in f:
            r = json.loads(line.strip() or "{}")
            d = r.get("date","")
            if d: recs[d] = round(float(r.get("pct",0) or 0), 4)
    idx_data[code] = recs

def stat(arr):
    if not arr: return {"count":0,"avg":0,"win":0}
    n = len(arr); avg = sum(arr)/n
    return {"count":n,"avg":round(avg,4),"win":round(sum(1 for v in arr if v>0)/n,4)}

# ═══════════════════════════════════════════
# STEP 1: 找每个指数的"日柱" — 60甲子中表现最好的那个干支
# ═══════════════════════════════════════════
sixty_pct = {code: defaultdict(list) for code in INDICES}
for td in sorted(idx_data["sh000001"].keys()):
    a = cache.get(td,{})
    gz = a.get("gzDay","")
    if not gz: continue
    for code in INDICES:
        pct = idx_data[code].get(td)
        if pct is not None: sixty_pct[code][gz].append(pct)

index_stem = {}
print("=" * 80)
print("4指数取象(日柱) — 60甲子中表现最好的干支")
print("=" * 80)
for code, name in INDICES.items():
    ranked = sorted([(gz, stat(arr)) for gz, arr in sixty_pct[code].items() if len(arr)>=3],
                    key=lambda x: -x[1]["avg"])
    best_gz, best_s = ranked[0]
    worst_gz, worst_s = sorted(ranked, key=lambda x: x[1]["avg"])[0]
    tg_best = best_gz[0]; dz_best = best_gz[1]
    tg_worst = worst_gz[0]; dz_worst = worst_gz[1]
    index_stem[code] = {"best": best_gz, "worst": worst_gz, "bestAvg": best_s["avg"], "worstAvg": worst_s["avg"]}
    print(f"  {name}: 日柱={best_gz}({TIANGAN_WUXING.get(tg_best,'?')}{DIZHI_WUXING.get(dz_best,'?')}) avg{best_s['avg']:+.2f}% n={best_s['count']}  "
          f"忌={worst_gz}({TIANGAN_WUXING.get(tg_worst,'?')}{DIZHI_WUXING.get(dz_worst,'?')}) {worst_s['avg']:+.2f}%")

# ═══════════════════════════════════════════
# STEP 2: 2026年逐月能量画像 + 走势预判 + 风险日历
# ═══════════════════════════════════════════
print()
print("=" * 80)
print("2026年 逐月能量 × 4指数走势 + 风险日历")
print("=" * 80)

# Group 2026 days by month
month_days_2026 = defaultdict(list)
for td in sorted(idx_data["sh000001"].keys()):
    if td[:4] != "2026": continue
    ym = td[:7]
    month_days_2026[ym].append(td)

# Wuxing interaction helpers
WUXING_SHENG = {"木":"火","火":"土","土":"金","金":"水","水":"木"}  # A生B
WUXING_KE = {"木":"土","土":"水","水":"火","火":"金","金":"木"}  # A克B

for ym in sorted(month_days_2026.keys()):
    tds = month_days_2026[ym]
    if len(tds) < 3: continue
    
    # month ganzhi from first trading day
    mgz = cache.get(tds[0],{}).get("gzMonth","??")
    mtg = mgz[0] if mgz else ""; mdz = mgz[1] if len(mgz)>1 else ""
    mwx_tg = TIANGAN_WUXING.get(mtg,"?"); mwx_dz = DIZHI_WUXING.get(mdz,"?")
    
    # month wuxing energy
    wx_power = defaultdict(int)
    wx_power[mwx_tg] += 2  # month stem = 2
    wx_power[mwx_dz] += 1  # month branch = 1
    # year = 丙午(火+火)
    wx_power["火"] += 5  # year dominates
    
    dominant = sorted(wx_power.items(), key=lambda x: -x[1])
    energy_desc = " > ".join(f"{w}({c})" for w,c in dominant)
    
    # month index stats
    monthly_stats = {}
    for code, name in INDICES.items():
        pcts = [idx_data[code][td] for td in tds if td in idx_data[code]]
        monthly_stats[code] = stat(pcts)
    
    # which indices benefit?
    beneficiaries = []
    for code, name in INDICES.items():
        best_gz = index_stem[code]["best"]
        bt = best_gz[0]; bd = best_gz[1]
        bwx_t = TIANGAN_WUXING.get(bt,""); bwx_d = DIZHI_WUXING.get(bd,"")
        # Does month energy support this index?
        support = 0
        if bwx_t in dominant and dominant[[w for w,_ in dominant].index(bwx_t)][1] >= 3: support += 2
        if bwx_d in dominant and dominant[[w for w,_ in dominant].index(bwx_d)][1] >= 3: support += 1
        if any(WUXING_SHENG.get(w,"") == bwx_t for w,_ in dominant): support += 1  # month sheng index
        if any(WUXING_SHENG.get(w,"") == bwx_d for w,_ in dominant): support += 1
        beneficiaries.append((name, support))
    
    beneficiaries.sort(key=lambda x: -x[1])
    
    print(f"\n{'─'*80}")
    print(f"【{ym}】{mgz}月  月干{mtg}({mwx_tg}) 月支{mdz}({mwx_dz})")
    print(f"  能量倾斜: {energy_desc}")
    print(f"  预计利好: {', '.join(f'{n}({s})' for n,s in beneficiaries[:4])}")
    
    # index monthly performance
    print(f"  {'指数':<6s} {'月累计':>8s} {'胜率':>6s} {'预判':>10s}")
    for code, name in INDICES.items():
        s = monthly_stats[code]
        bar = "+" if s["avg"] >= 0 else ""
        # Predict: if index stem matches dominant energy, should be good
        best_gz = index_stem[code]["best"]
        bt = best_gz[0]; bwx_t = TIANGAN_WUXING.get(bt,"")
        pred = "☆有利" if bwx_t in dict(dominant) and dict(dominant)[bwx_t] >= 3 else ("☆不利" if bwx_t not in dict(dominant) else "~中性")
        print(f"  {name:<6s} {bar}{s['avg']:>7.2f}% {s['win']:>5.0%} {pred:>10s}")
    
    # ── risk days in this month ──
    risk_days = []
    for td in tds:
        a = cache.get(td,{})
        gz = a.get("gzDay",""); tg = a.get("tg","")
        pi = a.get("phaseIdx",-1); ph = a.get("phaseName","")
        lunar = f"{a.get('lunarMonth','')}{a.get('lunarDay','')}"
        severity = 0
        reasons = []
        
        # Rule: 农历十五
        if "十五" in lunar:
            severity = max(severity, 3)
            reasons.append("满月日")
        # Rule: 残月
        if pi == 7:
            severity = max(severity, 1)
            reasons.append("残月")
        # Rule: 指数忌日
        for code, name in INDICES.items():
            if gz == index_stem[code]["worst"]:
                severity = max(severity, 3)
                reasons.append(f"{name}忌日({gz})")
        # Rule: 丙午日
        if gz == "丙午":
            severity = max(severity, 4)
            reasons.append("丙午日(火极)")
        # Rule: 月相转折
        if pi == 4:
            severity = max(severity, 2)
            reasons.append("满月日")
        
        if severity >= 2:
            risk_days.append((td, gz, lunar, ph, severity, reasons))
    
    if risk_days:
        print(f"\n  ⚠ 风险日:")
        for td, gz, lunar, ph, sev, reasons in risk_days:
            label = {2:"🔶谨慎",3:"🔴危险",4:"💀高危",5:"🌑极端"}.get(sev, "⚠注意")
            # show index pcts for high risk days
            idx_brief = " ".join(f"{INDICES[code]}={idx_data[code].get(td,0):+.2f}%" for code in INDICES)
            print(f"  {td} {gz}日 {lunar} {ph} L{sev} {label}  {', '.join(reasons)}")
            print(f"    → {idx_brief}")

print(f"\n{'═'*80}")
print("总结:")
print(f"  上证 日柱={index_stem['sh000001']['best']} 忌={index_stem['sh000001']['worst']}")
print(f"  深证 日柱={index_stem['sz399001']['best']} 忌={index_stem['sz399001']['worst']}")
print(f"  创业 日柱={index_stem['sz399006']['best']} 忌={index_stem['sz399006']['worst']}")
print(f"  科创 日柱={index_stem['sh000688']['best']} 忌={index_stem['sh000688']['worst']}")
