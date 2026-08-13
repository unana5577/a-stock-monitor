import json
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

from tyme4py.solar import SolarDay

TZ = ZoneInfo("Asia/Shanghai")
SYNODIC_MONTH_DAYS = 29.53058867
PHASE_NAMES = ["新月", "娥眉月", "上弦月", "盈凸月", "满月", "亏凸月", "下弦月", "残月"]
REF_NEW_MOON_UTC = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INDICES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
}

RANGE_START = "2025-05-01"
RANGE_END = "2026-06-13"

TIANGAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
DIZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}


def moon_phase_index(dt: date) -> tuple[int, float]:
    bj = datetime(dt.year, dt.month, dt.day, 12, 0, 0, tzinfo=TZ).astimezone(timezone.utc)
    days = (bj - REF_NEW_MOON_UTC).total_seconds() / 86400.0
    age = days % SYNODIC_MONTH_DAYS
    idx = int((age / SYNODIC_MONTH_DAYS) * 8.0 + 0.5) % 8
    return idx, float(age)


def day_astro(d: date) -> dict:
    sd = SolarDay.from_ymd(d.year, d.month, d.day)
    scd = sd.get_sixty_cycle_day()
    ld = sd.get_lunar_day()
    lunar_month = ld.get_lunar_month()
    phase_idx, moon_age = moon_phase_index(d)
    waxing = "盈" if phase_idx <= 3 else "亏"
    jiazi = scd.get_name().replace("日", "")
    tg = jiazi[0] if len(jiazi) >= 1 else ""
    dz = jiazi[1] if len(jiazi) >= 2 else ""
    return {
        "date": f"{d.year:04d}-{d.month:02d}-{d.day:02d}",
        "sixtyCycleDay": jiazi,
        "tianGan": tg,
        "tianGanWx": TIANGAN_WUXING.get(tg, ""),
        "diZhi": dz,
        "diZhiWx": DIZHI_WUXING.get(dz, ""),
        "sixtyCycleMonth": scd.get_month().get_name(),
        "lunarMonth": lunar_month.get_name() if lunar_month else "",
        "lunarDay": ld.get_name() if ld else "",
        "phaseIndex": phase_idx,
        "phaseName": PHASE_NAMES[phase_idx] if 0 <= phase_idx < len(PHASE_NAMES) else "",
        "moonAgeDays": round(moon_age, 3),
        "waxingWaning": waxing,
    }


def load_daily(code: str) -> dict[str, dict]:
    fp = os.path.join(ROOT, "data", "index", "daily", code, "daily.jsonl")
    if not os.path.exists(fp):
        return {}
    records = {}
    with open(fp) as f:
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
            records[d] = {"pct": round(pct, 4), "close": float(row.get("close", 0) or 0)}
    return records


def stat(arr):
    if not arr:
        return {"avgPct": 0, "winRate": 0, "count": 0, "maxPct": 0, "minPct": 0, "stdPct": 0}
    n = len(arr)
    avg = sum(arr) / n
    wins = sum(1 for v in arr if v > 0)
    mx = max(arr)
    mn = min(arr)
    var = sum((v - avg) ** 2 for v in arr) / n if n > 1 else 0
    return {
        "count": n, "avgPct": round(avg, 4), "winRate": round(wins / n, 4),
        "maxPct": round(mx, 4), "minPct": round(mn, 4), "stdPct": round(var ** 0.5, 4),
    }


def cumulative(arr):
    if not arr:
        return 0.0
    return round(sum(arr), 4)


def count_range_text(start_d, end_d):
    days = (end_d - start_d).days + 1
    return f"{start_d} ~ {end_d}（{days}个自然日）"


def cjk_pad(s, width=6):
    w = sum(2 if ord(c) > 127 else 1 for c in s)
    return s + " " * max(0, width + 4 - w)


def main():
    start = date.fromisoformat(RANGE_START)
    end = date.fromisoformat(RANGE_END)

    print("=" * 70)
    print("月相节点 × 4大盘 天时回测")
    print("=" * 70)

    all_days = []
    cur = start
    while cur <= end:
        all_days.append(day_astro(cur))
        cur = cur + timedelta(days=1)

    date_to_astro = {d["date"]: d for d in all_days}

    index_data = {}
    for code, name in INDICES.items():
        records = load_daily(code)
        index_data[code] = records

    trading_dates = set()
    for recs in index_data.values():
        trading_dates.update(recs.keys())
    trading_dates = sorted(trading_dates)
    in_range_tds = [td for td in trading_dates if td >= RANGE_START and td <= RANGE_END]

    index_range = {}
    for code, name in INDICES.items():
        recs = index_data[code]
        in_range = {k: v for k, v in recs.items() if RANGE_START <= k <= RANGE_END}
        index_range[code] = in_range

    full_recs = index_data["sh000001"]
    full_all = sorted(full_recs.keys())
    earliest = full_all[0] if full_all else "?"
    latest = full_all[-1] if full_all else "?"

    print()
    print("=" * 70)
    print("一、测试范围与数据概览")
    print("=" * 70)
    print(f"  测试区间: {RANGE_START} ~ {RANGE_END}（{(end - start).days + 1}个自然日）")
    print(f"  测试区间内交易日: {len(in_range_tds)} 天")
    print(f"  上证指数数据: {earliest} ~ {latest}（{len(full_all)}条日线）")
    print(f"  在区间内上证交易日: {len(index_range['sh000001'])} 天")
    for code, name in INDICES.items():
        recs = index_data[code]
        rkeys = sorted(recs.keys())
        in_r = len(index_range.get(code, {}))
        print(f"  {name}({code}): {rkeys[0] if rkeys else '?'} ~ {rkeys[-1] if rkeys else '?'}（{len(recs)}条日线，区间内{in_r}天）")
    print()

    print("=" * 70)
    print("二、逐月大盘表现（按自然月+月干支）")
    print("=" * 70)
    month_data = defaultdict(lambda: {code: [] for code in INDICES})
    month_ganzhi = {}
    month_all_dates = defaultdict(list)
    for td in in_range_tds:
        ym = td[:7]
        astro = date_to_astro.get(td, {})
        if not month_ganzhi.get(ym) and astro.get("sixtyCycleMonth"):
            month_ganzhi[ym] = astro["sixtyCycleMonth"]
        month_all_dates[ym].append(td)
        for code in INDICES:
            r = index_data[code].get(td)
            if r:
                month_data[ym][code].append(r["pct"])

    month_output = {}
    for ym in sorted(month_data.keys()):
        mgz = month_ganzhi.get(ym, "??")
        mgz_tg = mgz[0] if len(mgz) >= 1 else ""
        mgz_dz = mgz[1] if len(mgz) >= 2 else ""
        mgz_tg_wx = TIANGAN_WUXING.get(mgz_tg, "?")
        mgz_dz_wx = DIZHI_WUXING.get(mgz_dz, "?")

        month_output[ym] = {"monthGanzhi": mgz, "ganzhiWx": f"{mgz_tg_wx}{mgz_dz_wx}", "tradingDays": len(month_all_dates[ym])}
        print(f"\n  {ym} 【{mgz}（{mgz_tg_wx}{mgz_dz_wx}）】 交易日:{len(month_all_dates[ym])}天")
        best_name = None
        best_pct = -999
        worst_name = None
        worst_pct = 999
        for code, name in INDICES.items():
            s = stat(month_data[ym][code])
            month_output[ym][code] = s
            bar = "+" if s["avgPct"] >= 0 else ""
            marker = ""
            if s["avgPct"] >= 1.0:
                marker = " ★大涨"
            elif s["avgPct"] <= -1.0:
                marker = " ▼大跌"
            print(f"    {cjk_pad(name)} avg {bar}{s['avgPct']:.2f}%  win {s['winRate']:.0%}  n={s['count']}{marker}")
            if s["avgPct"] > best_pct:
                best_pct, best_name = s["avgPct"], name
            if s["avgPct"] < worst_pct:
                worst_pct, worst_name = s["avgPct"], name
        print(f"    → 本月最强: {best_name}({best_pct:+.2f}%)  最弱: {worst_name}({worst_pct:+.2f}%)")

    print()
    print(f"  区间总胜率: ", end="")
    for code, name in INDICES.items():
        all_pcts = []
        for ym in month_data:
            all_pcts.extend(month_data[ym][code])
        s = stat(all_pcts)
        print(f"{name} {s['winRate']:.0%}  ", end="")
    print()

    phase_nodes = {i: [] for i in range(8)}
    phase_daily = {i: {code: [] for code in INDICES} for i in range(8)}
    waxing_waning = {"盈": {code: [] for code in INDICES}, "亏": {code: [] for code in INDICES}}
    phase_transitions = {}

    for td in in_range_tds:
        astro = date_to_astro.get(td)
        if not astro:
            continue
        pi = astro["phaseIndex"]
        ww = astro["waxingWaning"]
        phase_nodes[pi].append(td)
        for code in INDICES:
            r = index_data[code].get(td)
            if r is not None:
                phase_daily[pi][code].append(r["pct"])
                waxing_waning[ww][code].append(r["pct"])

    for i, tds in enumerate(in_range_tds):
        if tds not in date_to_astro:
            continue
        pi = date_to_astro[tds]["phaseIndex"]
        for j in range(i + 1, min(i + 2, len(in_range_tds))):
            next_td = in_range_tds[j]
            if next_td not in date_to_astro:
                continue
            npi = date_to_astro[next_td]["phaseIndex"]
            if pi == npi:
                continue
            key_trans = f"{PHASE_NAMES[pi]}→{PHASE_NAMES[npi]}"
            if key_trans not in phase_transitions:
                phase_transitions[key_trans] = {code: [] for code in INDICES}
            for code in INDICES:
                r = index_data[code].get(next_td)
                if r is not None:
                    phase_transitions[key_trans][code].append(r["pct"])

    full_moon_dates = sorted(phase_nodes[4])[:10]
    new_moon_dates = sorted(phase_nodes[0])[:10]

    print()
    print("=" * 70)
    print("三、8个月相 × 4个指数 统计")
    print("=" * 70)
    print(f"  满月日({len(phase_nodes[4])}次): {', '.join(full_moon_dates)}")
    print(f"  新月日({len(phase_nodes[0])}次): {', '.join(new_moon_dates)}")
    print()
    by_phase_output = {}
    for pi in range(8):
        pname = PHASE_NAMES[pi]
        idx_stats = {}
        for code, name in INDICES.items():
            idx_stats[code] = stat(phase_daily[pi][code])
        by_phase_output[pi] = {"phaseName": pname, "nodeDays": len(phase_nodes[pi]), "indices": idx_stats}

        print(f"  【{pname}】 出现 {len(phase_nodes[pi])} 次")
        for code, name in INDICES.items():
            s = idx_stats[code]
            bar = "+" if s["avgPct"] >= 0 else ""
            print(f"    {cjk_pad(name)} avg {bar}{s['avgPct']:.2f}%  win {s['winRate']:.0%}  n={s['count']}  max={s['maxPct']:.2f}%  min={s['minPct']:.2f}%")

    print()
    print("=" * 70)
    print("四、盈/亏 半周期 × 4指数")
    print("=" * 70)
    ww_output = {}
    for ww in ["盈", "亏"]:
        idx_stats = {}
        for code, name in INDICES.items():
            idx_stats[code] = stat(waxing_waning[ww][code])
        ww_output[ww] = idx_stats
        print(f"\n  【{ww}】 (满月前→新月、满月后→残月)")
        for code, name in INDICES.items():
            s = idx_stats[code]
            bar = "+" if s["avgPct"] >= 0 else ""
            print(f"    {cjk_pad(name)} avg {bar}{s['avgPct']:.2f}%  win {s['winRate']:.0%}  n={s['count']}")

    print()
    print("=" * 70)
    print("五、关键月相节点 ±N天 转折分析")
    print("=" * 70)
    node_analysis = {"full_moon": {}, "new_moon": {}, "first_quarter": {}, "last_quarter": {}}

    for node_type, target_phase in [("full_moon", 4), ("new_moon", 0), ("first_quarter", 2), ("last_quarter", 6)]:
        node_dates = phase_nodes[target_phase]
        print(f"\n  ── {PHASE_NAMES[target_phase]} 节点 ({len(node_dates)} 次) ──")

        windows = {
            "前3天→当日": {"offset_range": range(-3, 1), "label": "前3→当日"},
            "前1天→当日": {"offset_range": range(-1, 1), "label": "前1→当日"},
            "当日→后1天": {"offset_range": range(0, 2), "label": "当日→后1"},
            "当日→后3天": {"offset_range": range(0, 4), "label": "当日→后3"},
        }

        for win_name, win_cfg in windows.items():
            pcts_by_idx = {code: [] for code in INDICES}
            for nd in node_dates:
                ndt = date.fromisoformat(nd)
                window_dates = []
                for off in win_cfg["offset_range"]:
                    wd = ndt + timedelta(days=off)
                    wds = wd.isoformat()
                    if wds in trading_dates:
                        window_dates.append(wds)
                if len(window_dates) < 2:
                    continue
                for code in INDICES:
                    vals = [index_data[code].get(d, {}).get("pct") for d in window_dates if d in index_data[code]]
                    vals = [v for v in vals if v is not None]
                    if len(vals) >= 2:
                        pcts_by_idx[code].append(cumulative(vals))

            if any(len(v) >= 3 for v in pcts_by_idx.values()):
                print(f"    {win_cfg['label']}:")
                for code, name in INDICES.items():
                    s = stat(pcts_by_idx[code]) if pcts_by_idx[code] else None
                    if s and s["count"] >= 3:
                        bar = "+" if s["avgPct"] >= 0 else ""
                        print(f"      {cjk_pad(name)} avg {bar}{s['avgPct']:.2f}%  win {s['winRate']:.0%}  n={s['count']}")

        for code in INDICES:
            node_analysis[node_type][code] = {}
            for win_name, win_cfg in windows.items():
                pcts = []
                for nd in node_dates:
                    ndt = date.fromisoformat(nd)
                    window_dates = []
                    for off in win_cfg["offset_range"]:
                        wd = ndt + timedelta(days=off)
                        wds = wd.isoformat()
                        if wds in trading_dates:
                            window_dates.append(wds)
                    if len(window_dates) < 2:
                        continue
                    vals = [index_data[code].get(d, {}).get("pct") for d in window_dates if d in index_data[code]]
                    vals = [v for v in vals if v is not None]
                    if len(vals) >= 2:
                        pcts.append(cumulative(vals))
                node_analysis[node_type][code][win_cfg["label"]] = stat(pcts) if pcts else stat([])

    print()
    print("=" * 70)
    print("六、大跌日画像（上证/深证日跌幅 < -2%）")
    print("=" * 70)
    DROP_THRESHOLD = -2.0
    crash_days = []
    for td in in_range_tds:
        sh_pct = (index_data["sh000001"].get(td) or {}).get("pct")
        sz_pct = (index_data["sz399001"].get(td) or {}).get("pct")
        if (sh_pct is not None and sh_pct <= DROP_THRESHOLD) or (sz_pct is not None and sz_pct <= DROP_THRESHOLD):
            astro = date_to_astro.get(td, {})
            crash_days.append({
                "date": td,
                "shPct": sh_pct,
                "szPct": sz_pct,
                "ganzhi": astro.get("sixtyCycleDay", ""),
                "phase": astro.get("phaseName", ""),
                "phaseIdx": astro.get("phaseIndex", -1),
                "tianGan": astro.get("tianGan", ""),
                "tianGanWx": astro.get("tianGanWx", ""),
                "diZhi": astro.get("diZhi", ""),
                "month": td[:7],
                "monthGanzhi": astro.get("sixtyCycleMonth", ""),
            })

    if crash_days:
        print(f"  共 {len(crash_days)} 个大跌日（阈值 < {DROP_THRESHOLD}%）:")
        print()
        for cd in crash_days:
            sh_s = f"上证{cd['shPct']:+.2f}%" if cd["shPct"] is not None else ""
            sz_s = f"深证{cd['szPct']:+.2f}%" if cd["szPct"] is not None else ""
            print(f"  {cd['date']} {cd['ganzhi']}日({cd['tianGanWx']}) {cd['phase']} [{cd['monthGanzhi']}] {sh_s} {sz_s}")

        print()
        print("  大跌日干支分布:")
        tg_cnt = defaultdict(int)
        for cd in crash_days:
            tg_cnt[cd["tianGan"]] += 1
        for tg, cnt in sorted(tg_cnt.items(), key=lambda x: -x[1]):
            wx = TIANGAN_WUXING.get(tg, "?")
            print(f"    {tg}({wx}): {cnt}次")

        print()
        print("  大跌日月相分布:")
        phase_cnt = defaultdict(int)
        for cd in crash_days:
            phase_cnt[cd["phase"]] += 1
        for ph, cnt in sorted(phase_cnt.items(), key=lambda x: -x[1]):
            print(f"    {ph}: {cnt}次")

        print()
        print("  大跌日月份分布:")
        month_cnt = defaultdict(int)
        for cd in crash_days:
            month_cnt[cd["month"]] += 1
        for m, cnt in sorted(month_cnt.items(), key=lambda x: -x[1]):
            mgz = crash_days[0]["monthGanzhi"] if crash_days else ""
            for cd in crash_days:
                if cd["month"] == m:
                    mgz = cd["monthGanzhi"]
                    break
            print(f"    {m}({mgz}): {cnt}次")
    else:
        print("  区间内无大跌日（阈值 < -2%）")

    print()
    print("=" * 70)
    print("七、月相转换次日涨跌 (样本≥3)")
    print("=" * 70)
    trans_output = {}
    for trans_key, by_code in sorted(phase_transitions.items()):
        stats = {}
        for code, name in INDICES.items():
            s = stat(by_code[code])
            stats[code] = s
        trans_output[trans_key] = stats
        has_sample = any(s["count"] >= 3 for s in stats.values())
        if has_sample:
            print(f"\n    {trans_key}:")
            for code, name in INDICES.items():
                s = stats[code]
                if s["count"] >= 3:
                    bar = "+" if s["avgPct"] >= 0 else ""
                    print(f"      {cjk_pad(name)} avg {bar}{s['avgPct']:.2f}%  win {s['winRate']:.0%}  n={s['count']}")

    outdir = os.path.join(ROOT, "data", "astro", "backtest")
    os.makedirs(outdir, exist_ok=True)
    out = {
        "range": {"start": RANGE_START, "end": RANGE_END},
        "calendarDays": len(all_days),
        "tradingDaysInRange": len(in_range_tds),
        "indexCoverage": {code: {"totalRecords": len(index_data[code]), "inRange": len(index_range.get(code, {})), "earliest": min(index_data[code].keys()) if index_data[code] else "", "latest": max(index_data[code].keys()) if index_data[code] else ""} for code in INDICES},
        "monthlySummary": month_output,
        "byPhase": by_phase_output,
        "byWaxingWaning": ww_output,
        "nodeAnalysis": node_analysis,
        "crashDays": crash_days,
        "phaseTransitions": trans_output,
    }
    outpath = os.path.join(outdir, "phase_stats.json")
    with open(outpath, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n落盘: {outpath}")


if __name__ == "__main__":
    main()
