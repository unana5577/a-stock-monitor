import json
import os
from datetime import date, datetime, timedelta, timezone as tz_mod
from zoneinfo import ZoneInfo
from collections import defaultdict

from tyme4py.solar import SolarDay

TZ = ZoneInfo("Asia/Shanghai")
SYNODIC_MONTH_DAYS = 29.53058867
PHASE_NAMES = ["新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"]
REF_NEW_MOON_UTC = datetime(2000, 1, 6, 18, 14, tzinfo=tz_mod.utc)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

TIANGAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
DIZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}
WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

INDICES = {
    "sh000001": "上证指数", "sz399001": "深证成指",
    "sz399006": "创业板指", "sh000688": "科创50",
}

ETF_SYMBOLS = [
    "sh512480", "sh515880", "sh516510", "sh516010",
    "sh563530", "sh562500", "sh515120", "sh516160", "sh512400",
]
ETF_NAMES = {
    "sh512480": "半导体", "sh515880": "通信", "sh516510": "云计算",
    "sh516010": "游戏", "sh563530": "商航", "sh562500": "机器人",
    "sh515120": "创新药", "sh516160": "新能源", "sh512400": "有色",
}
ETF_WUXING_GUESS = {
    "sh512480": ["火", "土"], "sh515880": ["水", "火"], "sh516510": ["水"],
    "sh516010": ["水"], "sh563530": ["火", "金"], "sh562500": ["金"],
    "sh515120": ["木"], "sh516160": ["火"], "sh512400": ["土"],
}

RANGE_START = "2025-05-01"
RANGE_END = "2026-06-13"
CURRENT_YEAR_GANZHI = "乙巳"


def moon_phase_index(dt: date) -> tuple[int, float]:
    bj = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=TZ).astimezone(tz_mod.utc)
    days = (bj - REF_NEW_MOON_UTC).total_seconds() / 86400.0
    age = days % SYNODIC_MONTH_DAYS
    idx = int((age / SYNODIC_MONTH_DAYS) * 8.0 + 0.5) % 8
    return idx, float(age)


def day_astro(d: date) -> dict:
    sd = SolarDay.from_ymd(d.year, d.month, d.day)
    scd = sd.get_sixty_cycle_day()
    jiazi = scd.get_name().replace("日", "")
    tg = jiazi[0] if len(jiazi) >= 1 else ""
    dz = jiazi[1] if len(jiazi) >= 2 else ""
    month_jiazi = scd.get_month().get_name()
    mtg = month_jiazi[0] if len(month_jiazi) >= 1 else ""
    mdz = month_jiazi[1] if len(month_jiazi) >= 2 else ""
    phase_idx, _ = moon_phase_index(d)
    year_tg = CURRENT_YEAR_GANZHI[0]
    year_dz = CURRENT_YEAR_GANZHI[1]
    return {
        "date": f"{d.year:04d}-{d.month:02d}-{d.day:02d}",
        "sixtyCycleDay": jiazi, "tianGan": tg, "tianGanWx": TIANGAN_WUXING.get(tg, ""),
        "diZhi": dz, "diZhiWx": DIZHI_WUXING.get(dz, ""),
        "sixtyCycleMonth": month_jiazi,
        "monthTianGan": mtg, "monthTianGanWx": TIANGAN_WUXING.get(mtg, ""),
        "monthDiZhi": mdz, "monthDiZhiWx": DIZHI_WUXING.get(mdz, ""),
        "yearTianGan": year_tg, "yearTianGanWx": TIANGAN_WUXING.get(year_tg, ""),
        "yearDiZhi": year_dz, "yearDiZhiWx": DIZHI_WUXING.get(year_dz, ""),
        "phaseIndex": phase_idx,
        "phaseName": PHASE_NAMES[phase_idx] if 0 <= phase_idx < len(PHASE_NAMES) else "",
    }


def load_daily_jsonl(path: str) -> dict[str, dict]:
    records = {}
    if not os.path.exists(path):
        return records
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            d = str(row.get("date", "")).strip()
            if not d:
                continue
            pct = float(row.get("pct", row.get("Pct", 0.0)) or 0.0)
            records[d] = {"pct": round(pct, 4)}
    return records


def stat(arr):
    if not arr:
        return {"avgPct": 0, "winRate": 0, "count": 0, "maxPct": 0, "minPct": 0}
    n = len(arr)
    avg = sum(arr) / n
    return {"count": n, "avgPct": round(avg, 4), "winRate": round(sum(1 for v in arr if v > 0) / n, 4),
            "maxPct": round(max(arr), 4), "minPct": round(min(arr), 4)}


def pearson_r(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0, n
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return 0.0, n
    r = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (sx * sy) ** 0.5
    return round(r, 4), n


def cjk_pad(s, width=6):
    w = sum(2 if ord(c) > 127 else 1 for c in s)
    return s + " " * max(0, width + 4 - w)


def bold(v, threshold=0.8):
    return f"\033[1m{v}\033[0m" if abs(v) >= threshold else str(v)


def wuxing_signature(ganzhi_str):
    tg = ganzhi_str[0] if len(ganzhi_str) >= 1 else "?"
    dz = ganzhi_str[1] if len(ganzhi_str) >= 2 else "?"
    return f"{TIANGAN_WUXING.get(tg, '?')}{DIZHI_WUXING.get(dz, '?')}"


def monthly_wuxing_energy(mgz):
    tg = mgz[0] if len(mgz) >= 1 else ""
    dz = mgz[1] if len(mgz) >= 2 else ""
    wx_cnt = defaultdict(int)
    wx_cnt[TIANGAN_WUXING.get(tg, "")] += 2
    wx_cnt[DIZHI_WUXING.get(dz, "")] += 1
    return dict(wx_cnt)


def year_wuxing_energy():
    wx_cnt = defaultdict(int)
    wx_cnt[TIANGAN_WUXING.get(CURRENT_YEAR_GANZHI[0], "")] += 3
    wx_cnt[DIZHI_WUXING.get(CURRENT_YEAR_GANZHI[1], "")] += 2
    return dict(wx_cnt)


def main():
    start = date.fromisoformat(RANGE_START)
    end = date.fromisoformat(RANGE_END)

    print("=" * 90)
    print(f"  天时能量 × A股回测 综合报告 V3")
    print(f"  测试区间: {RANGE_START} ~ {RANGE_END} | 流年: {CURRENT_YEAR_GANZHI}")
    print("=" * 90)

    all_days = []
    cur = start
    while cur <= end:
        all_days.append(day_astro(cur))
        cur = cur + timedelta(days=1)
    date_to_astro = {d["date"]: d for d in all_days}

    records = {}
    for code in INDICES:
        fp = os.path.join(ROOT, "data", "index", "daily", code, "daily.jsonl")
        records[code] = load_daily_jsonl(fp)
    for sym in ETF_SYMBOLS:
        fp = os.path.join(ROOT, "data", "etf", "daily", sym, "daily.jsonl")
        records[sym] = load_daily_jsonl(fp)

    trading_dates = sorted(set().union(*[recs.keys() for recs in records.values()]))
    in_range_tds = [td for td in trading_dates if RANGE_START <= td <= RANGE_END]
    print(f"  交易日: {len(in_range_tds)}天  |  日历: {len(all_days)}天\n")

    # =====================================================================
    # SECTION 1: 每次新月窗口 ±3天明细
    # =====================================================================
    print("=" * 90)
    print("一、每次新月窗口 ±3天 明细（Q1：新月是否有规律性反弹？）")
    print("=" * 90)

    new_moon_dates = sorted([td for td in in_range_tds if date_to_astro.get(td, {}).get("phaseIndex") == 0])

    new_moon_windows = defaultdict(dict)
    for nm in new_moon_dates:
        nm_dt = date.fromisoformat(nm)
        nm_astro = date_to_astro.get(nm, {})
        window_key = nm[:7]
        if window_key not in new_moon_windows:
            new_moon_windows[window_key] = []
        window_days = []
        for off in range(-3, 4):
            wd = nm_dt + timedelta(days=off)
            wds = wd.isoformat()
            if wds in in_range_tds:
                window_days.append(wds)
        new_moon_windows[window_key].append({"nmDate": nm, "nmGanzhi": nm_astro.get("sixtyCycleDay", ""),
                                               "nmPhase": nm_astro.get("phaseName", ""),
                                               "monthGanzhi": nm_astro.get("sixtyCycleMonth", ""),
                                               "days": window_days})

    total_nm = 0
    win_nm = 0
    loss_nm = 0
    for yyyymm in sorted(new_moon_windows.keys()):
        for win_info in new_moon_windows[yyyymm]:
            total_nm += 1
            nm_date = win_info["nmDate"]
            nm_gz = win_info["nmGanzhi"]
            mgz = win_info["monthGanzhi"]
            days = win_info["days"]

            tp = []  # trading days with data
            for d in days:
                sh_pct = (records["sh000001"].get(d) or {}).get("pct")
                if sh_pct is not None:
                    tp.append(d)

            if len(tp) < 2:
                continue

            cumul = {code: 1.0 for code in INDICES}
            all_up = True
            for code in INDICES:
                for d in tp:
                    r = records[code].get(d)
                    if r:
                        cumul[code] *= (1 + r["pct"] / 100)
            cumul_ret = {code: round((cumul[code] - 1) * 100, 2) for code in INDICES}

            nm_day_pct = {code: (records[code].get(nm_date) or {}).get("pct", 0) for code in INDICES}
            nm_day_up = all(p >= 0 for p in nm_day_pct.values() if p is not None)

            tag = ""
            if any(c >= 2.0 for c in cumul_ret.values()):
                tag = " ★★强反弹"
                win_nm += 1
            elif all(c > 0 for c in cumul_ret.values()):
                tag = " ★温和反弹"
                win_nm += 1
            elif any(c <= -2.0 for c in cumul_ret.values()):
                tag = " ✗大跌窗口"
                loss_nm += 1
            elif all(c < 0 for c in cumul_ret.values()):
                tag = " ✗偏弱"
                loss_nm += 1
            else:
                tag = " ~震荡"

            print(f"\n  新月#{total_nm}: {nm_date} {nm_gz}日（{mgz}）{tag}")
            print(f"  {'日期':<14s} {'干支':<8s} {'月相':<8s}  上证   深证   创业   科创")
            for d in tp:
                astro = date_to_astro.get(d, {})
                gz = astro.get("sixtyCycleDay", "")
                ph = astro.get("phaseName", "")
                parts = []
                for code in INDICES:
                    r = records[code].get(d)
                    if r:
                        bar = "+" if r["pct"] >= 0 else ""
                        parts.append(f"{bar}{r['pct']:>7.2f}%")
                    else:
                        parts.append("      -")
                print(f"  {d:<14s} {gz:<8s} {ph:<8s}  {' '.join(parts)}")
            parts = []
            for code in INDICES:
                bar = "+" if cumul_ret[code] >= 0 else ""
                parts.append(f"{bar}{cumul_ret[code]:>6.2f}%")
            print(f"  {'累积':>14s} {'':>8s} {'':>8s}  {' '.join(parts)}")

    print(f"\n  新月窗口汇总: 反弹{win_nm}/{total_nm} 大跌{loss_nm}/{total_nm}")
    print(f"  反弹比例: {win_nm}/{total_nm} = {win_nm/total_nm:.0%}" if total_nm else "")

    # =====================================================================
    # SECTION 2: 每次满月→亏凸月转折明细
    # =====================================================================
    print()
    print("=" * 90)
    print("二、每次满月→亏凸月转折（Q2：月满则亏是否成立？）")
    print("=" * 90)

    full_moon_dates = sorted([td for td in in_range_tds if date_to_astro.get(td, {}).get("phaseIndex") == 4])
    fm_result = {"total": 0, "decline": 0, "rise": 0, "decline_after3": 0, "rise_after3": 0, "details": []}

    for idx_fm, fm in enumerate(full_moon_dates):
        fm_dt = date.fromisoformat(fm)
        fm_astro = date_to_astro.get(fm, {})
        mgz = fm_astro.get("sixtyCycleMonth", "")
        fm_pcts = {code: (records[code].get(fm) or {}).get("pct", 0) for code in INDICES}

        after_days = []
        for off in range(1, 5):
            wd = fm_dt + timedelta(days=off)
            wds = wd.isoformat()
            if wds in in_range_tds:
                after_days.append(wds)

        if len(after_days) < 2:
            continue
        fm_result["total"] += 1

        after_cumul = {code: 1.0 for code in INDICES}
        for code in INDICES:
            for d in after_days[:3]:
                r = records[code].get(d)
                if r:
                    after_cumul[code] *= (1 + r["pct"] / 100)
        after3_ret = {code: round((after_cumul[code] - 1) * 100, 2) for code in INDICES}

        sh_after3 = after3_ret["sh000001"]
        if sh_after3 < 0:
            fm_result["decline_after3"] += 1
        else:
            fm_result["rise_after3"] += 1

        sh_fm = fm_pcts["sh000001"]
        if sh_fm is not None and sh_fm < 0:
            fm_result["decline"] += 1
        elif sh_fm is not None:
            fm_result["rise"] += 1

        tag = " ✓月满转弱" if sh_after3 < -0.5 else (" ✗不跌反涨" if sh_after3 > 0.5 else " ~震荡")

        print(f"\n  满月#{idx_fm+1}: {fm} {fm_astro.get('sixtyCycleDay','')}日（{mgz}）{tag}")
        print(f"    满月日: ", end="")
        for code, name in INDICES.items():
            p = fm_pcts.get(code, 0) or 0
            bar = "+" if p >= 0 else ""
            print(f"{name} {bar}{p:.2f}%  ", end="")
        print()
        print(f"    后3天累积: ", end="")
        for code, name in INDICES.items():
            bar = "+" if after3_ret[code] >= 0 else ""
            print(f"{name} {bar}{after3_ret[code]:.2f}%  ", end="")
        print()

        fm_result["details"].append({"date": fm, "monthGanzhi": mgz, "after3Ret": after3_ret})

    print(f"\n  满月后3天累积: 下跌{fm_result['decline_after3']}/{fm_result['total']} "
          f"上涨{fm_result['rise_after3']}/{fm_result['total']}")
    if fm_result['total']:
        rate = fm_result['decline_after3'] / fm_result['total']
        print(f'  "月满则亏"命中率: {fm_result["decline_after3"]}/{fm_result["total"]} = {rate:.0%}')

    # =====================================================================
    # SECTION 2.5: 新月/满月 × 干支匹配
    # =====================================================================
    print()
    print("=" * 90)
    print("附：新月/满月 × 干支匹配（Q1：哪些干支组合下新月反弹/失效？）")
    print("=" * 90)

    nm_ganzhi_stats = defaultdict(lambda: {"rebound": 0, "crash": 0, "neutral": 0, "examples": []})
    fm_ganzhi_stats = defaultdict(lambda: {"decline": 0, "rise": 0, "neutral": 0, "examples": []})

    # 重新收集新月窗口的更精微统计
    for yyyymm in sorted(new_moon_windows.keys()):
        for win_info in new_moon_windows[yyyymm]:
            nm_date = win_info["nmDate"]
            nm_gz = win_info["nmGanzhi"]
            mgz = win_info["monthGanzhi"]
            tg = nm_gz[0] if nm_gz else ""
            tg_wx = TIANGAN_WUXING.get(tg, "?")
            days = win_info["days"]

            cumul = {code: 1.0 for code in INDICES}
            for code in INDICES:
                for d in days:
                    r = records[code].get(d)
                    if r:
                        cumul[code] *= (1 + r["pct"] / 100)
            cumul_sh = round((cumul["sh000001"] - 1) * 100, 2)

            key = f"{nm_gz}({tg_wx})"
            if cumul_sh >= 1.5:
                nm_ganzhi_stats[key]["rebound"] += 1
                nm_ganzhi_stats[key]["examples"].append(f"{nm_date}:累积{cumul_sh:+.1f}%")
            elif cumul_sh <= -1.5:
                nm_ganzhi_stats[key]["crash"] += 1
                nm_ganzhi_stats[key]["examples"].append(f"{nm_date}:累积{cumul_sh:+.1f}%")
            else:
                nm_ganzhi_stats[key]["neutral"] += 1

    for fm, fm_astro in [(td, date_to_astro.get(td, {})) for td in full_moon_dates]:
        fm_gz = fm_astro.get("sixtyCycleDay", "")
        tg = fm_gz[0] if fm_gz else ""
        tg_wx = TIANGAN_WUXING.get(tg, "?")
        mgz = fm_astro.get("sixtyCycleMonth", "")
        after3 = fm_result["details"]
        match_fm = [a for a in after3 if a["date"] == fm]
        if not match_fm:
            continue
        sh_after3 = match_fm[0]["after3Ret"].get("sh000001", 0)

        key = f"{fm_gz}({tg_wx})"
        if sh_after3 <= -1.0:
            fm_ganzhi_stats[key]["decline"] += 1
            fm_ganzhi_stats[key]["examples"].append(f"{fm}:后3天{sh_after3:+.1f}%")
        elif sh_after3 >= 1.0:
            fm_ganzhi_stats[key]["rise"] += 1
            fm_ganzhi_stats[key]["examples"].append(f"{fm}:后3天{sh_after3:+.1f}%")
        else:
            fm_ganzhi_stats[key]["neutral"] += 1

    print(f"\n  新月日干支 × 反弹/大跌:")
    print(f"  {'干支组合':<20s} {'★反弹':>6s} {'✗大跌':>6s} {'~震荡':>6s}  案例")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6}  {'-'*30}")
    for key, v in sorted(nm_ganzhi_stats.items(),
                          key=lambda x: x[1]["rebound"] + x[1]["crash"] + x[1]["neutral"], reverse=True):
        if v["rebound"] + v["crash"] + v["neutral"] >= 1:
            print(f"  {key:<20s} {v['rebound']:>6d} {v['crash']:>6d} {v['neutral']:>6d}   "
                  f"{', '.join(v['examples'][:3])}")

    print(f"\n  满月日干支 × 后3天方向:")
    print(f"  {'干支组合':<20s} {'▼转弱':>6s} {'▲反涨':>6s} {'~平':>6s}  案例")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6}  {'-'*30}")
    for key, v in sorted(fm_ganzhi_stats.items(),
                          key=lambda x: x[1]["decline"] + x[1]["rise"] + x[1]["neutral"], reverse=True):
        if v["decline"] + v["rise"] + v["neutral"] >= 1:
            print(f"  {key:<20s} {v['decline']:>6d} {v['rise']:>6d} {v['neutral']:>6d}   "
                  f"{', '.join(v['examples'][:3])}")

    # 天干分组统计
    print(f"\n  新月按日干聚合:")
    tg_nm = defaultdict(lambda: {"rebound": 0, "crash": 0, "total": 0})
    for key, v in nm_ganzhi_stats.items():
        tg = key[0] if key else ""
        tg_nm[tg]["rebound"] += v["rebound"]
        tg_nm[tg]["crash"] += v["crash"]
        tg_nm[tg]["total"] += v["rebound"] + v["crash"] + v["neutral"]
    for tg in TIANGAN:
        d = tg_nm[tg]
        if d["total"] >= 2:
            ratio = d["rebound"] / d["total"] * 100 if d["total"] else 0
            bar = "█" * int(ratio / 10)
            print(f"    {tg}({TIANGAN_WUXING.get(tg,'?')}日): "
                  f"反弹 {d['rebound']}/{d['total']} ({ratio:.0f}%) {bar}")

    print(f"\n  满月按日干聚合:")
    tg_fm = defaultdict(lambda: {"decline": 0, "total": 0})
    for key, v in fm_ganzhi_stats.items():
        tg = key[0] if key else ""
        tg_fm[tg]["decline"] += v["decline"]
        tg_fm[tg]["total"] += v["decline"] + v["rise"] + v["neutral"]
    for tg in TIANGAN:
        d = tg_fm[tg]
        if d["total"] >= 2:
            ratio = d["decline"] / d["total"] * 100 if d["total"] else 0
            bar = "█" * int(ratio / 10)
            print(f"    {tg}({TIANGAN_WUXING.get(tg,'?')}日): "
                  f"后3天跌 {d['decline']}/{d['total']} ({ratio:.0f}%) {bar}")

    # =====================================================================
    # SECTION 3: 因子列表 + 相关性贡献拆解
    # =====================================================================
    print()
    print("=" * 90)
    print("三、信号合成器因子拆解（Q3：有哪些因子？每个贡献多大？）")
    print("=" * 90)

    print("""
  当前因子体系:

  ┌─────────────────────────────────────────────────────────┐
  │ F1: 日干得分 (W1)                                       │
  │   含义: ETF在"日干=甲/乙/..."下的历史平均涨跌            │
  │   训练: 全部历史数据取平均                              │
  │   粒度: 10个天干 × 9个ETF                              │
  ├─────────────────────────────────────────────────────────┤
  │ F2: 日干×月干 交互得分 (W2)                             │
  │   含义: 同是"丙日"，但"月干=甲"vs"月干=壬"下表现不同     │
  │   训练: (月干, 日干) 组合的平均涨跌                     │
  │   粒度: 10×10=100个组合 × 9个ETF                       │
  ├─────────────────────────────────────────────────────────┤
  │ F3: 日干×年干 交互得分 (W3)                             │
  │   含义: 同是"丙日"，但在乙巳年背景下的特殊表现           │
  │   训练: (年干, 日干) 组合的平均涨跌                     │
  │   粒度: 10×10=100个组合 × 9个ETF                       │
  └─────────────────────────────────────────────────────────┘
""")

    day_score_raw = {sym: defaultdict(list) for sym in ETF_SYMBOLS}
    interaction_dm_raw = {sym: defaultdict(list) for sym in ETF_SYMBOLS}
    interaction_dy_raw = {sym: defaultdict(list) for sym in ETF_SYMBOLS}
    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        mtg = astro.get("monthTianGan", "")
        ytg = astro.get("yearTianGan", "")
        if not tg:
            continue
        for sym in ETF_SYMBOLS:
            r = records[sym].get(td)
            if r is None:
                continue
            day_score_raw[sym][tg].append(r["pct"])
            interaction_dm_raw[sym][f"{mtg}{tg}"].append(r["pct"])
            interaction_dy_raw[sym][f"{ytg}{tg}"].append(r["pct"])

    day_score = {}
    dm_score = {}
    dy_score = {}
    for sym in ETF_SYMBOLS:
        day_score[sym] = {tg: round(sum(arr) / len(arr), 4) if arr else 0.0 for tg, arr in day_score_raw[sym].items()}
        dm_score[sym] = {k: round(sum(arr) / len(arr), 2) for k, arr in interaction_dm_raw[sym].items() if len(arr) >= 3}
        dy_score[sym] = {k: round(sum(arr) / len(arr), 2) for k, arr in interaction_dy_raw[sym].items() if len(arr) >= 3}

    weights = {}
    signals_by_sym = {sym: [] for sym in ETF_SYMBOLS}
    actuals_by_sym = {sym: [] for sym in ETF_SYMBOLS}

    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        mtg = astro.get("monthTianGan", "")
        ytg = astro.get("yearTianGan", "")
        if not tg or not mtg or not ytg:
            continue
        for sym in ETF_SYMBOLS:
            r = records[sym].get(td)
            if r is None:
                continue
            s1 = day_score[sym].get(tg, 0)
            s2 = dm_score[sym].get(f"{mtg}{tg}", 0)
            s3 = dy_score[sym].get(f"{ytg}{tg}", 0)
            signals_by_sym[sym].append((s1, s2, s3))
            actuals_by_sym[sym].append(r["pct"])

    for sym in ETF_SYMBOLS:
        best_r = -2
        best_w = (1.0, 0.2, 0.1)
        for w1 in [0.5, 1.0, 1.5, 2.0]:
            for w2 in [0.0, 0.1, 0.2, 0.3, 0.5]:
                for w3 in [0.0, 0.05, 0.1, 0.2]:
                    preds = [w1 * s[0] + w2 * s[1] + w3 * s[2] for s in signals_by_sym[sym]]
                    r, n = pearson_r(preds, actuals_by_sym[sym])
                    if r > best_r:
                        best_r = r
                        best_w = (w1, w2, w3)
        weights[sym] = {"w1": best_w[0], "w2": best_w[1], "w3": best_w[2], "r": best_r}

    r_f1 = {}
    r_f12 = {}
    r_f123 = {}
    for sym in ETF_SYMBOLS:
        s_list = signals_by_sym[sym]
        a_list = actuals_by_sym[sym]
        w = (weights[sym]["w1"], weights[sym]["w2"], weights[sym]["w3"])
        p_f1 = [s[0] for s in s_list]
        p_f12 = [w[0] * s[0] + w[1] * s[1] for s in s_list]
        p_f123 = [w[0] * s[0] + w[1] * s[1] + w[2] * s[2] for s in s_list]
        r_f1[sym] = pearson_r(p_f1, a_list)[0]
        r_f12[sym] = pearson_r(p_f12, a_list)[0]
        r_f123[sym] = pearson_r(p_f123, a_list)[0]

    print(f"  {'ETF':<10s} {'r(F1)':>8s} {'→+F2':>8s} {'→+F3':>8s} {'提升':>8s}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for sym in ETF_SYMBOLS:
        delta = r_f123[sym] - r_f1[sym]
        delta_s = f"+{delta:+.4f}" if delta >= 0 else f"{delta:+.4f}"
        print(f"  {cjk_pad(ETF_NAMES.get(sym,sym)):<10s} "
              f"{r_f1[sym]:>+8.4f} {r_f12[sym]:>+8.4f} {r_f123[sym]:>+8.4f} {delta_s:>8s}")
    avg_delta = sum(r_f123[s] - r_f1[s] for s in ETF_SYMBOLS) / len(ETF_SYMBOLS)
    print(f"\n  平均提升: {avg_delta:+.4f}  → 叠加交互因子{'有效' if avg_delta > 0.01 else '效果不明显'}")

    print(f"\n  候选扩展因子（待实现）:")
    print(f"  - F4: 地支三合局（日支×月支×年支 是否构成申子辰/巳酉丑等合局）")
    print(f"  - F5: 月相调节（满月日权重×0.8、新月日权重×1.2）")
    print(f"  - F6: 六十甲子纳音（甲子=海中金、乙丑=海中金...）")
    print(f"  - 调试方法: 新增因子→重跑→比较r→留用提升>0.01的因子")

    # =====================================================================
    # SECTION 4: 逐步叠加验证
    # =====================================================================
    print()
    print("=" * 90)
    print("四、逐步叠加验证（Q4：年→月→日是否逐步有效？）")
    print("=" * 90)
    print(f"  逻辑: 年(乙巳木火) → 月(各月干支) → 日(各日干支)")
    print(f"  验证方法: 对比三层分别预测的相关性提升\n")

    print(f"  纯日干预测(F1):")
    print(f"    只看日干，忽略年/月背景")
    for sym in ETF_SYMBOLS[:5]:
        print(f"    {cjk_pad(ETF_NAMES.get(sym,sym)):<10s} r={r_f1[sym]:+.4f}")

    print(f"\n  日干+月干背景(F1+F2):")
    print(f"    日干×月干交互，比如'丙日+月甲'vs'丙日+月壬'区分开")
    for sym in ETF_SYMBOLS[:5]:
        print(f"    {cjk_pad(ETF_NAMES.get(sym,sym)):<10s} r={r_f12[sym]:+.4f}")

    print(f"\n  日干+月干+年干全层(F1+F2+F3):")
    print(f"    日+月+年全交互")
    for sym in ETF_SYMBOLS[:5]:
        print(f"    {cjk_pad(ETF_NAMES.get(sym,sym)):<10s} r={r_f123[sym]:+.4f}")

    print(f"\n  结论: 叠加是否有效看r的提升幅度。当前平均{avg_delta:+.4f}")
    print(f"  如果F3(年干)提升极小→年干可能不重要；如果F2(月干)显著提升→月背景是关键")

    # =====================================================================
    # SECTION 5: 流月五行能量 × ETF交叉验证
    # =====================================================================
    print()
    print("=" * 90)
    print("五、流月五行能量 × ETF交叉验证（Q5：能量偏斜有预测价值吗？）")
    print("=" * 90)

    month_order = []
    seen = set()
    for td in sorted(trading_dates):
        mgz = date_to_astro.get(td, {}).get("sixtyCycleMonth", "")
        if mgz and mgz not in seen:
            seen.add(mgz)
            month_order.append(mgz)

    month_etf_pct = defaultdict(lambda: defaultdict(list))
    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        mgz = astro.get("sixtyCycleMonth", "")
        if not mgz:
            continue
        for sym in ETF_SYMBOLS:
            r = records[sym].get(td)
            if r:
                month_etf_pct[mgz][sym].append(r["pct"])

    yw = year_wuxing_energy()
    print(f"  年能量: ", end="")
    for w, c in sorted(yw.items(), key=lambda x: -x[1]):
        print(f"{w}({c}) ", end="")
    print()

    theory_hit = 0
    theory_total = 0

    for mgz in month_order[:13]:
        etfs = month_etf_pct[mgz]
        if not etfs:
            continue
        mw = monthly_wuxing_energy(mgz)
        combined = defaultdict(int)
        for w, c in yw.items():
            combined[w] += c
        for w, c in mw.items():
            combined[w] += c
        dominant = sorted(combined.items(), key=lambda x: -x[1])
        strong_wx = [w for w, c in dominant if c >= max(combined.values()) * 0.6]
        weak_wx = [w for w, c in dominant if c <= 1]

        print(f"\n  【{mgz}】 月能量: ", end="")
        for w, c in sorted(mw.items(), key=lambda x: -x[1]):
            print(f"{w}({c}) ", end="")
        print(f"→ 偏盛: {'/'.join(strong_wx)}")

        for sym in ETF_SYMBOLS:
            arr = etfs.get(sym, [])
            if len(arr) < 3:
                continue
            s = stat(arr)
            guess_wx = ETF_WUXING_GUESS.get(sym, [])
            bar = "+" if s["avgPct"] >= 0 else ""
            theory = ""
            for gw in guess_wx:
                if gw in strong_wx:
                    theory += f"同气共振(预期涨) " if s["avgPct"] > 0 else f"同气但跌✗ "
                if any(sg in WUXING_SHENG and WUXING_SHENG[sg] == gw for sg in strong_wx):
                    theory += f"被生(预期涨) " if s["avgPct"] > 0 else f"被生但跌✗ "
                if any(sg in WUXING_KE and WUXING_KE[sg] == gw for sg in strong_wx):
                    theory += f"被克(预期跌) " if s["avgPct"] < 0 else f"被克但涨✗ "
                if any(gw == WUXING_KE.get(sg, "") for sg in strong_wx):
                    theory += f"克月(预期平或跌) "

            if "✗" in theory:
                theory_hit += 0
            elif theory:
                theory_hit += 1
            theory_total += (1 if theory else 0)

            print(f"    {cjk_pad(ETF_NAMES.get(sym,sym))} avg {bar}{s['avgPct']:.2f}%  "
                  f"win {s['winRate']:.0%}  n={s['count']}  {theory}")

    if theory_total > 0:
        print(f"\n  五行理论预测正确率: {theory_hit}/{theory_total} = {theory_hit/theory_total:.0%}")
        print(f"  注: 样本太少(每月只有1个总平均)，目前只能做方向性验证")

    # =====================================================================
    # SECTION 6: 信号合成器当前预测
    # =====================================================================
    print()
    print("=" * 90)
    print("六、信号合成器当前预测（最近7个交易日）")
    print("=" * 90)

    predict_dates = []
    for td in reversed(in_range_tds):
        if len(predict_dates) >= 7:
            break
        if date_to_astro.get(td, {}).get("tianGan", ""):
            predict_dates.append(td)
    predict_dates.sort()

    correct_strong = 0
    total_strong = 0

    for td in predict_dates:
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        mtg = astro.get("monthTianGan", "")
        ytg = astro.get("yearTianGan", "")
        ph = astro.get("phaseName", "")
        mgz = astro.get("sixtyCycleMonth", "")

        print(f"\n  {td} {astro.get('sixtyCycleDay','')}日 {ph} [{mgz}]")
        print(f"    年{ytg}({TIANGAN_WUXING.get(ytg,'?')}) "
              f"月{mtg}({TIANGAN_WUXING.get(mtg,'?')}) "
              f"日{tg}({TIANGAN_WUXING.get(tg,'?')})")
        print(f"  {'ETF':<10s} {'信号':>8s} {'预测':>8s} {'实际':>8s} {'命中':>6s}")
        print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")

        for sym in ETF_SYMBOLS:
            w = weights[sym]
            s1 = day_score[sym].get(tg, 0)
            s2 = dm_score[sym].get(f"{mtg}{tg}", 0)
            s3 = dy_score[sym].get(f"{ytg}{tg}", 0)
            sig = w["w1"] * s1 + w["w2"] * s2 + w["w3"] * s3
            actual = records[sym].get(td, {}).get("pct")

            stars = ""
            if sig >= 0.8: stars = "★★★"
            elif sig >= 0.4: stars = "★★"
            elif sig >= 0.15: stars = "★"
            elif sig <= -0.8: stars = "☆☆☆"
            elif sig <= -0.4: stars = "☆☆"
            elif sig <= -0.15: stars = "☆"

            bias = "看多" if sig > 0.1 else ("看空" if sig < -0.1 else "中性")
            bar_act = "+" if (actual or 0) >= 0 else ""
            actual_s = f"{bar_act}{actual:.2f}%" if actual is not None else "-"

            hit = ""
            if abs(sig) >= 0.15 and actual is not None:
                total_strong += 1
                if (sig > 0 and actual > 0) or (sig < 0 and actual < 0):
                    correct_strong += 1
                    hit = " ✓"
                else:
                    hit = " ✗"

            print(f"  {cjk_pad(ETF_NAMES.get(sym,sym)):<10s} {sig:>+8.2f} {bias:>8s} {actual_s:>8s} {hit:>6s}")

    if total_strong > 0:
        print(f"\n  强信号命中: {correct_strong}/{total_strong} = {correct_strong/total_strong:.0%}")

    # =====================================================================
    # SECTION 7: 质量评估 + 调试建议
    # =====================================================================
    print()
    print("=" * 90)
    print("七、信号合成器质量评估 + 调试建议")
    print("=" * 90)

    all_preds = []
    all_actuals = []
    strong_preds = []
    strong_actuals = []
    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        mtg = astro.get("monthTianGan", "")
        ytg = astro.get("yearTianGan", "")
        if not tg or not mtg or not ytg:
            continue
        for sym in ETF_SYMBOLS:
            w = weights[sym]
            s1 = day_score[sym].get(tg, 0)
            s2 = dm_score[sym].get(f"{mtg}{tg}", 0)
            s3 = dy_score[sym].get(f"{ytg}{tg}", 0)
            sig = w["w1"] * s1 + w["w2"] * s2 + w["w3"] * s3
            r = records[sym].get(td)
            if r is None:
                continue
            all_preds.append(sig)
            all_actuals.append(r["pct"])
            if abs(sig) >= 0.5:
                strong_preds.append(sig)
                strong_actuals.append(r["pct"])

    overall_r, n = pearson_r(all_preds, all_actuals)
    corr, _ = 0, 0
    if strong_preds:
        corr, _ = pearson_r(strong_preds, strong_actuals)

    dir_correct = sum(1 for i in range(n) if (all_preds[i] > 0 and all_actuals[i] > 0) or (all_preds[i] < 0 and all_actuals[i] < 0))
    total_nz = sum(1 for i in range(n) if all_preds[i] != 0 and all_actuals[i] != 0)
    strong_correct = sum(1 for i in range(len(strong_preds)) if (strong_preds[i] > 0 and strong_actuals[i] > 0) or (strong_preds[i] < 0 and strong_actuals[i] < 0))

    print(f"  全样本 r = {overall_r:+.4f}  (n={n})")
    print(f"  方向正确率 = {dir_correct}/{total_nz} = {dir_correct/max(total_nz,1):.1%}")
    print(f"  强信号 r = {corr:+.4f}  (n={len(strong_preds)})")
    print(f"  强信号方向正确率 = {strong_correct}/{max(len(strong_preds),1)} = "
          f"{strong_correct/max(len(strong_preds),1):.1%}")
    print()
    print(f"  ┌──────────────────────────────────────────────────────┐")
    print(f"  │ 调试建议                                             │")
    print(f"  ├──────────────────────────────────────────────────────┤")
    print(f"  │ 1. 当前 r={overall_r:+.2f} 处于中等水平，可提升        │")
    print(f"  │ 2. 先跑更多数据（等数据积攒到500+天再重训）         │")
    print(f"  │ 3. 新增F4(地支三合局)、F5(月相调节)后重跑对比r     │")
    print(f"  │ 4. 用留出法验证: 最后30天不训练，纯验证              │")
    print(f"  │ 5. 强信号(|sig|>0.5)命中率={strong_correct/max(len(strong_preds),1):.1%}，优先用强信号做决策  │")
    print(f"  └──────────────────────────────────────────────────────┘")

    outdir = os.path.join(ROOT, "data", "astro", "backtest")
    os.makedirs(outdir, exist_ok=True)
    out = {
        "range": {"start": RANGE_START, "end": RANGE_END},
        "newMoonWindows": {k: v for k, v in new_moon_windows.items()},
        "fullMoonAfter3": fm_result,
        "factorContributions": {"r_f1_only": r_f1, "r_f12": r_f12, "r_f123": r_f123},
        "weights": weights,
        "overallR": overall_r,
        "strongSignalAccuracy": round(strong_correct / max(len(strong_preds), 1), 4),
    }
    with open(os.path.join(outdir, "full_report.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n落盘: {os.path.join(outdir, 'full_report.json')}")


if __name__ == "__main__":
    main()
