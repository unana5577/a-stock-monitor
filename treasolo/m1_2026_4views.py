"""2026年 4指数四条独立报告 — 逐月逐日明细 + 日柱能量交互"""
import json, os
from datetime import date, timedelta
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INDICES = {"sh000001":"上证","sz399001":"深证","sz399006":"创业","sh000688":"科创"}
T_WX = {"甲":"木","乙":"木","丙":"火","丁":"火","戊":"土","己":"土","庚":"金","辛":"金","壬":"水","癸":"水"}
D_WX = {"子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火","午":"火","未":"土","申":"金","酉":"金","戌":"土","亥":"水"}
PHASE = ["新月","娥眉月","上弦月","盈凸月","满月","亏凸月","下弦月","残月"]
WX_SHENG = {"木":"火","火":"土","土":"金","金":"水","水":"木"}
WX_KE = {"木":"土","土":"水","水":"火","火":"金","金":"木"}

# load
cache = {}
with open(os.path.join(ROOT,"data","astro","astro_calendar.jsonl")) as f:
    for l in f:
        r = json.loads(l.strip()); cache[r["date"]] = r

idx = {}
for code in INDICES:
    recs = {}
    fp = os.path.join(ROOT,"online_debug_data","index",f"{code}_daily.jsonl")
    for l in open(fp):
        r = json.loads(l.strip() or "{}"); d = r.get("date","")
        if d: recs[d] = round(float(r.get("pct",0) or 0), 4)
    idx[code] = recs

# ── compute each index's 日柱 ──
gz_pct = {c: defaultdict(list) for c in INDICES}
for td in sorted(idx["sh000001"]):
    gz = cache.get(td,{}).get("gzDay","")
    if not gz: continue
    for c in INDICES:
        p = idx[c].get(td)
        if p is not None: gz_pct[c][gz].append(p)

idx_stem = {}
for c, n in INDICES.items():
    ranked = sorted([(gz, sum(arr)/len(arr), len(arr)) for gz,arr in gz_pct[c].items() if len(arr)>=5],
                    key=lambda x: -x[1])
    gz, avg, cnt = ranked[0]; worst = sorted(ranked,key=lambda x: x[1])[0]
    idx_stem[c] = {"stem": gz, "avg": round(avg,4), "cnt": cnt, "worst": worst[0], "worstAvg": round(worst[1],4)}

# ── energy interaction function ──
def stem_energy(stem):
    """for a ganzhi like 甲寅, return wuxing breakdown"""
    t = stem[0] if stem else ""; d = stem[1] if len(stem)>1 else ""
    return {"天干": T_WX.get(t,"?"), "地支": D_WX.get(d,"?"), "完整": f"{T_WX.get(t,'?')}{D_WX.get(d,'?')}"}

def interact(idx_stem_str, month_stem_str, year_stem_str):
    """how does month+year energy interact with index stem?"""
    i_e = stem_energy(idx_stem_str)
    m_e = stem_energy(month_stem_str)
    y_e = stem_energy(year_stem_str)
    
    clues = []
    # Check: month supports index?
    for k in ["天干","地支"]:
        iw = i_e[k]; mw = m_e[k]
        if iw == mw: clues.append(f"月{k}同气({iw})")
        elif WX_SHENG.get(mw)=="": pass
        if WX_SHENG.get(mw)=="": pass
    
    # full element check
    i_wx = set([i_e["天干"],i_e["地支"]])
    m_wx = set([m_e["天干"],m_e["地支"]])
    y_wx = set([y_e["天干"],y_e["地支"]])
    
    for iw in i_wx:
        for mw in m_wx:
            if iw == mw: clues.append(f"月{iw}同气")
            elif WX_SHENG.get(mw)=="": pass
            if WX_SHENG.get(mw)==iw: clues.append(f"月{mw}生{iw}(有利)")
            if WX_KE.get(mw)==iw: clues.append(f"月{mw}克{iw}(不利)")
            if WX_SHENG.get(iw)==mw: clues.append(f"指数{iw}生月{mw}(耗气)")
            if WX_KE.get(iw)==mw: clues.append(f"指数{iw}克月{mw}(压制)")
    
    return list(set(clues))

# ═══════════════════════════════════
# 为每个指数输出独立报告
# ═══════════════════════════════════

tds_2026 = sorted([td for td in idx["sh000001"] if td[:4]=="2026"])

for code, name in INDICES.items():
    istem = idx_stem[code]["stem"]
    print(f"\n{'═'*100}")
    print(f"  {name}({code})  日柱={istem}  历史avg={idx_stem[code]['avg']:+.2f}%({idx_stem[code]['cnt']}次)  忌={idx_stem[code]['worst']} 忌日avg={idx_stem[code]['worstAvg']:+.2f}%")
    print(f"{'═'*100}")
    
    # group by month
    months = defaultdict(list)
    for td in tds_2026:
        months[td[:7]].append(td)
    
    for ym in sorted(months):
        tds = months[ym]
        mgz = cache.get(tds[0],{}).get("gzMonth","??")
        ygz = cache.get(tds[0],{}).get("gzYear","??")
        mtg = mgz[0] if mgz else ""; mdz = mgz[1] if len(mgz)>1 else ""
        ytg = ygz[0] if ygz else ""; ydz = ygz[1] if len(ygz)>1 else ""
        mse = stem_energy(mgz); yse = stem_energy(ygz)
        
        clues = interact(istem, mgz, ygz)
        
        # month stats for this index
        month_pcts = [idx[code][td] for td in tds if td in idx[code]]
        cumul = 1.0
        for p in month_pcts: cumul *= (1 + p/100)
        cumul_ret = round((cumul-1)*100, 2)
        wins = sum(1 for p in month_pcts if p > 0)
        
        favorable = any("有利" in c or "同气" in c for c in clues)
        unfavorable = any("不利" in c or "克" in c and "生" not in c for c in clues) if clues else False
        
        print(f"\n  ┌─ {ym} ──────────────────────────────────────────────")
        print(f"  │ 流年: {ygz} 天干{ytg}({yse['天干']}) 地支{ydz}({yse['地支']}) → 背景能量: {yse['完整']}")
        print(f"  │ 流月: {mgz} 天干{mtg}({mse['天干']}) 地支{mdz}({mse['地支']}) → 月能量: {mse['完整']}")
        print(f"  │ {name}日柱{istem}: {stem_energy(istem)['完整']}")
        print(f"  │ 交互: {'; '.join(clues[:6]) if clues else '(无明显交互)'}")
        print(f"  │ 预判: {'✓ 有利' if favorable else ('✗ 不利' if unfavorable else '~ 中性')}")
        print(f"  │ 月累积: {cumul_ret:+.2f}%  胜率: {wins}/{len(month_pcts)}={wins/max(len(month_pcts),1):.0%}")
        print(f"  ├{'─'*70}")
        print(f"  │ {'日期':<12s} {'日干支':<8s} {'月相':<6s} {'涨跌':>8s} {'风险标记':<20s}")
        print(f"  ├{'─'*70}")
        
        for td in tds:
            a = cache.get(td,{})
            gz = a.get("gzDay",""); ph = a.get("phaseName","")
            pct = idx[code].get(td, 0)
            if pct is None: pct = 0
            bar = "+" if pct >= 0 else ""
            
            # risk flags for this specific index+day
            flags = []
            if gz == idx_stem[code]["worst"]: flags.append(f"忌日({gz})")
            if a.get("lunarDay","") and "十五" in a.get("lunarDay",""): flags.append("满月")
            if a.get("phaseIdx") == 7: flags.append("残月")
            if a.get("phaseIdx") == 4: flags.append("满月")
            # multi-index risk: 丙午 is common worst
            if gz == "丙午": flags.append("丙午火极")
            
            flag_str = ",".join(flags) if flags else ""
            flag_color = ""
            if "忌日" in flag_str: flag_color = "🔴"
            elif len(flags) >= 2: flag_color = "🟡"
            elif flags: flag_color = "⚪"
            
            pct_viz = ""
            if pct >= 2: pct_viz = " ↑↑"
            elif pct >= 1: pct_viz = " ↑"
            elif pct <= -2: pct_viz = " ↓↓"
            elif pct <= -1: pct_viz = " ↓"
            
            print(f"  │ {td:<12s} {gz:<8s} {ph:<6s} {bar}{pct:>7.2f}%{pct_viz:<4s} {flag_color} {flag_str}")
        
        print(f"  └{'─'*70}")

# ═══════════════════════════════════
print(f"\n{'═'*100}")
print("算法调优建议")
print(f"{'═'*100}")
print("""
  当前模型: 日柱五行 × 流月流年五行 → 生克关系 → 定性(有利/不利)
  
  问题: 1) 只用天干地支的五行, 没用到六十甲子的纳音和合冲
       2) 权重是手工定的(同气=+2,被生=+1,被克=-1), 没有数据驱动
       3) 没有区分"月干"和"月支"的影响力差异
  
  调优路线:
  
  Phase 1 — 基础验证 (当前)
    - 用每天的实际涨跌 vs 日柱能量关系, 统计方向正确率
    - 计算出 "同气日正确率" "被克日正确率" "被生日正确率"
    - 目标: 方向正确率 > 55% 就说明模型有信号
  
  Phase 2 — 权重校准
    - 对每条规则(同气/被生/被克/月相转换)做逻辑回归
    - 输出每条规则的 β 系数, 代表该规则的实际影响力
    - 例如: "同气 β=0.12" → 同气日平均比普通日高 0.12%
  
  Phase 3 — 加纳音和合冲
    - 六十甲子每个都有纳音五行 (如甲子=海中金)
    - 日柱 × 月支的六合/六冲/三合局 — 这个在八字里很重要
    - 月相节点作为调节变量 (满月日权重打8折)
  
  Phase 4 — 多指数联合模型
    - 不独立看每个指数, 而是看"当科创被克时, 资金是否流向创业/深证"
    - 构建一个板块轮动倾向矩阵
""")
