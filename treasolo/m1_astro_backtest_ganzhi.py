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

INDICES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
}

ETF_SYMBOLS = [
    "sh512480", "sh515880", "sh516510", "sh516010",
    "sh563530", "sh562500", "sh515120", "sh516160", "sh512400",
]

ETF_NAMES = {
    "sh512480": "半导体ETF", "sh515880": "通信ETF", "sh516510": "云计算ETF",
    "sh516010": "游戏ETF", "sh563530": "商业航天ETF", "sh562500": "机器人ETF",
    "sh515120": "创新药ETF", "sh516160": "新能源ETF", "sh512400": "有色金属ETF",
}

ETF_WUXING_GUESS = {
    "sh512480": ["金"], "sh515880": ["金"], "sh516510": ["水"],
    "sh516010": ["火"], "sh563530": ["火", "金"], "sh562500": ["金"],
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
    ld = sd.get_lunar_day()
    lunar_month = ld.get_lunar_month()
    phase_idx, moon_age = moon_phase_index(d)

    jiazi = scd.get_name().replace("日", "")
    tg = jiazi[0] if len(jiazi) >= 1 else ""
    dz = jiazi[1] if len(jiazi) >= 2 else ""
    month_jiazi = scd.get_month().get_name()

    year_tg = CURRENT_YEAR_GANZHI[0] if len(CURRENT_YEAR_GANZHI) >= 1 else ""
    year_dz = CURRENT_YEAR_GANZHI[1] if len(CURRENT_YEAR_GANZHI) >= 2 else ""
    mtg = month_jiazi[0] if len(month_jiazi) >= 1 else ""
    mdz = month_jiazi[1] if len(month_jiazi) >= 2 else ""

    year_wx = TIANGAN_WUXING.get(year_tg, "")
    month_wx = TIANGAN_WUXING.get(mtg, "")
    day_wx = TIANGAN_WUXING.get(tg, "")

    return {
        "date": f"{d.year:04d}-{d.month:02d}-{d.day:02d}",
        "sixtyCycleDay": jiazi,
        "tianGan": tg, "tianGanWx": day_wx,
        "diZhi": dz, "diZhiWx": DIZHI_WUXING.get(dz, ""),
        "sixtyCycleMonth": month_jiazi,
        "monthTianGan": mtg, "monthTianGanWx": month_wx,
        "yearTianGanWx": year_wx,
        "tripleWx": f"{year_wx}+{month_wx}+{day_wx}",
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
            records[d] = {"pct": round(pct, 4), "close": float(row.get("close", 0) or 0)}
    return records


def stat(arr):
    if not arr:
        return {"avgPct": 0, "winRate": 0, "count": 0, "maxPct": 0, "minPct": 0}
    n = len(arr)
    avg = sum(arr) / n
    wins = sum(1 for v in arr if v > 0)
    return {"count": n, "avgPct": round(avg, 4), "winRate": round(wins / n, 4),
            "maxPct": round(max(arr), 4), "minPct": round(min(arr), 4)}


def cjk_pad(s, width=6):
    w = sum(2 if ord(c) > 127 else 1 for c in s)
    return s + " " * max(0, width + 4 - w)


def group_stats(pct_groups):
    out = {}
    for key, arr in sorted(pct_groups.items()):
        st = stat(arr)
        if st["count"] >= 2:
            out[key] = st
    return out


def rank_keys(stats, key="avgPct", top=5):
    items = [(k, v) for k, v in stats.items() if v["count"] >= 3]
    items.sort(key=lambda x: -x[1][key])
    return items[:top]


def main():
    start = date.fromisoformat(RANGE_START)
    end = date.fromisoformat(RANGE_END)

    print("=" * 70)
    print(f"干支五行×板块ETF 能量分析 V2（流年流月流日叠加）")
    print("=" * 70)

    all_days = []
    cur = start
    while cur <= end:
        all_days.append(day_astro(cur))
        cur = cur + timedelta(days=1)
    date_to_astro = {d["date"]: d for d in all_days}

    all_data = {}
    all_data.update(INDICES)
    for sym in ETF_SYMBOLS:
        all_data[sym] = ETF_NAMES.get(sym, sym)

    records = {}
    for code in all_data:
        fp = (os.path.join(ROOT, "data", "index", "daily", code, "daily.jsonl")
              if code in INDICES
              else os.path.join(ROOT, "data", "etf", "daily", code, "daily.jsonl"))
        recs = load_daily_jsonl(fp)
        records[code] = recs

    trading_dates = set()
    for recs in records.values():
        trading_dates.update(recs.keys())
    trading_dates = sorted(trading_dates)
    in_range_tds = [td for td in trading_dates if RANGE_START <= td <= RANGE_END]

    print()
    print("=" * 70)
    print("一、测试范围与数据概览")
    print("=" * 70)
    print(f"  测试区间: {RANGE_START} ~ {RANGE_END}（{(end - start).days + 1}个自然日）")
    print(f"  测试区间内交易日: {len(in_range_tds)} 天")
    print(f"  当前流年: {CURRENT_YEAR_GANZHI}（{TIANGAN_WUXING.get(CURRENT_YEAR_GANZHI[0], '?')}{DIZHI_WUXING.get(CURRENT_YEAR_GANZHI[1], '?')}）")
    print()
    for code in all_data:
        recs = records[code]
        rkeys = sorted(recs.keys())
        in_r = sum(1 for k in rkeys if RANGE_START <= k <= RANGE_END)
        name = all_data[code]
        print(f"  {name}({code}): {rkeys[0] if rkeys else '?'} ~ {rkeys[-1] if rkeys else '?'}（{len(recs)}条，区间内{in_r}天）")

    tian_gan_pct = {}
    tian_gan_pct_wx = {}
    di_zhi_pct = {}
    di_zhi_pct_wx = {}
    month_ganzhi_pct = {}
    triple_pct = {}

    for td in in_range_tds:
        astro = date_to_astro.get(td)
        if not astro:
            continue
        tg = astro["tianGan"]
        tg_wx = astro["tianGanWx"]
        dz = astro["diZhi"]
        dz_wx = astro["diZhiWx"]
        mgz = astro["sixtyCycleMonth"]
        triple = astro["tripleWx"]

        for code in all_data:
            r = records[code].get(td)
            if r is None:
                continue
            pct = r["pct"]

            for grp, gk in [(tian_gan_pct, tg), (tian_gan_pct_wx, tg_wx),
                              (di_zhi_pct, dz), (di_zhi_pct_wx, dz_wx),
                              (month_ganzhi_pct, mgz), (triple_pct, triple)]:
                if not gk:
                    continue
                if code not in grp:
                    grp[code] = {}
                grp[code].setdefault(gk, []).append(pct)

    print()
    print("=" * 70)
    print("二、流年流月流日三维五行叠加 ★核心★")
    print("=" * 70)
    print(f"  流年: {CURRENT_YEAR_GANZHI}({TIANGAN_WUXING.get(CURRENT_YEAR_GANZHI[0],'?')}{DIZHI_WUXING.get(CURRENT_YEAR_GANZHI[1],'?')})")
    print(f"  逻辑: 每天 = yearWx + monthWx + dayWx，统计日干在不同年干月干背景下的实际表现")

    triple_all = {}
    for code in all_data:
        st = triple_pct.get(code, {})
        for k, arr in st.items():
            if k not in triple_all:
                triple_all[k] = {}
            triple_all[k][code] = arr

    significant_triples = []
    for triple_key in sorted(triple_all.keys()):
        by_code = triple_all[triple_key]
        total_n = sum(len(arr) for arr in by_code.values())
        if total_n >= 3:
            significant_triples.append((triple_key, total_n))

    shown = 0
    for triple_key, total_n in sorted(significant_triples, key=lambda x: -x[1])[:20]:
        by_code = triple_all[triple_key]
        has_interesting = False
        lines = []
        for sym in ETF_SYMBOLS:
            arr = by_code.get(sym, [])
            s = stat(arr)
            if s["count"] >= 2:
                bar = "+" if s["avgPct"] >= 0 else ""
                lines.append(f"      {cjk_pad(ETF_NAMES[sym])} avg {bar}{s['avgPct']:.2f}%  win {s['winRate']:.0%}  n={s['count']}")
                if abs(s["avgPct"]) >= 0.5:
                    has_interesting = True
        if has_interesting:
            shown += 1
            wx_parts = triple_key.split("+")
            wx_label = f"年{wx_parts[0]}+月{wx_parts[1]}+日{wx_parts[2]}"
            if shown <= 10:
                print(f"\n  【{wx_label}】 出现 {total_n} 次")
                for l in lines:
                    print(l)

    print()
    print("=" * 70)
    print("三、初始 ETF 取象（后续用数据修订）")
    print("=" * 70)
    for sym in ETF_SYMBOLS:
        print(f"  {ETF_NAMES[sym]}({sym}): {'/'.join(ETF_WUXING_GUESS.get(sym, []))}")

    print()
    print("=" * 70)
    print("四、各 ETF 在 10 天干日下的表现 → 取象反推")
    print("=" * 70)
    for sym in ETF_SYMBOLS:
        name = ETF_NAMES[sym]
        guess_wx = "/".join(ETF_WUXING_GUESS.get(sym, []))
        stats = group_stats(tian_gan_pct.get(sym, {}))
        if not stats:
            continue
        top = rank_keys(stats, "avgPct", 5)
        bottom = rank_keys(stats, "avgPct", top=999)
        bottom = sorted(bottom, key=lambda x: x[1]["avgPct"])[:3]

        print(f"\n  【{name}】 初拟取象: {guess_wx}")
        print(f"    ★ 最佳天干:")
        for k, v in top:
            wx = TIANGAN_WUXING.get(k, "?")
            bar = "+" if v["avgPct"] >= 0 else ""
            print(f"      {k}({wx}日)  avg {bar}{v['avgPct']:.2f}%  win {v['winRate']:.0%}  n={v['count']}")
        print(f"    ☆ 最差天干:")
        for k, v in bottom:
            wx = TIANGAN_WUXING.get(k, "?")
            print(f"      {k}({wx}日)  avg {v['avgPct']:.2f}%  win {v['winRate']:.0%}  n={v['count']}")

        suggested_wx = {}
        for k, v in top:
            if v["avgPct"] > 0 and v["count"] >= 3:
                wx = TIANGAN_WUXING.get(k, "?")
                suggested_wx[wx] = suggested_wx.get(wx, 0) + v["avgPct"]
        if suggested_wx:
            best = sorted(suggested_wx.items(), key=lambda x: -x[1])
            suggested = [b[0] for b in best if b[1] > 0]
            if suggested:
                print(f"    → 数据建议取象: {'/'.join(suggested[:2])}")

    print()
    print("=" * 70)
    print("五、逐月 ETF 取向（流月干支 × 各ETF 涨跌）")
    print("=" * 70)
    month_order = []
    seen = set()
    for td in sorted(trading_dates):
        if td not in date_to_astro:
            continue
        mgz = date_to_astro[td]["sixtyCycleMonth"]
        if mgz not in seen:
            seen.add(mgz)
            month_order.append(mgz)
    month_order = month_order[:14]

    for mgz in month_order:
        mgz_tg = mgz[0] if mgz else ""
        mgz_dz = mgz[1] if len(mgz) > 1 else ""
        mgz_tg_wx = TIANGAN_WUXING.get(mgz_tg, "?")
        mgz_dz_wx = DIZHI_WUXING.get(mgz_dz, "?")

        print(f"\n  【{mgz} ({mgz_tg_wx}{mgz_dz_wx})】")
        for sym in ETF_SYMBOLS:
            arr = (month_ganzhi_pct.get(sym, {}) or {}).get(mgz)
            if arr is None:
                continue
            s = stat(arr)
            name = ETF_NAMES[sym]
            guess = "/".join(ETF_WUXING_GUESS.get(sym, []))
            bar = "+" if s["avgPct"] >= 0 else ""
            marker = " ★" if s["avgPct"] >= 1.5 else (" ▼" if s["avgPct"] <= -1.0 else "")
            print(f"    {cjk_pad(name+'('+guess+')')} avg {bar}{s['avgPct']:.2f}%  win {s['winRate']:.0%}  n={s['count']}{marker}")

    print()
    print("=" * 70)
    print("六、大跌日 ETF 特征（ETF日跌幅 < -3%）")
    print("=" * 70)
    DROP_THRESHOLD = -3.0
    crash_days = []
    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        etf_pcts = {}
        any_crash = False
        for sym in ETF_SYMBOLS:
            r = records[sym].get(td)
            pct = r["pct"] if r else None
            if pct is not None:
                etf_pcts[sym] = pct
                if pct <= DROP_THRESHOLD:
                    any_crash = True
        if any_crash:
            crash_days.append({
                "date": td,
                "ganzhi": astro.get("sixtyCycleDay", ""),
                "tianGan": astro.get("tianGan", ""),
                "tianGanWx": astro.get("tianGanWx", ""),
                "phase": astro.get("phaseName", ""),
                "phaseIdx": astro.get("phaseIndex", -1),
                "month": td[:7],
                "monthGanzhi": astro.get("sixtyCycleMonth", ""),
                "tripleWx": astro.get("tripleWx", ""),
                "etfPcts": etf_pcts,
            })

    if crash_days:
        print(f"  共 {len(crash_days)} 个 ETF 大跌日（阈值 < {DROP_THRESHOLD}%）:\n")
        for cd in crash_days:
            crashing = [f"{ETF_NAMES.get(s,s)}({pct:+.2f}%)" for s, pct in cd["etfPcts"].items() if pct <= DROP_THRESHOLD]
            print(f"  {cd['date']} {cd['ganzhi']}日({cd['tianGanWx']}) {cd['phase']} [{cd['monthGanzhi']}] 三维:{cd['tripleWx']}")
            print(f"    大跌品种: {', '.join(crashing)}")

        print()
        print("  大跌日天干分布:")
        tg_cnt = defaultdict(int)
        for cd in crash_days:
            tg_cnt[cd["tianGan"]] += 1
        for tg, cnt in sorted(tg_cnt.items(), key=lambda x: -x[1]):
            wx = TIANGAN_WUXING.get(tg, "?")
            print(f"    {tg}({wx}日): {cnt}次")

        print()
        print("  大跌日月相分布:")
        phase_cnt = defaultdict(int)
        for cd in crash_days:
            phase_cnt[cd["phase"]] += 1
        for ph, cnt in sorted(phase_cnt.items(), key=lambda x: -x[1]):
            print(f"    {ph}: {cnt}次")

        print()
        print("  大跌日月度分布:")
        month_cnt = defaultdict(int)
        for cd in crash_days:
            month_cnt[cd["month"]] += 1
        for m, cnt in sorted(month_cnt.items(), key=lambda x: -x[1]):
            mgz = ""
            for cd in crash_days:
                if cd["month"] == m:
                    mgz = cd["monthGanzhi"]
                    break
            print(f"    {m}({mgz}): {cnt}次")
    else:
        print("  区间内无 ETF 大跌日（阈值 < -3%）")

    print()
    print("=" * 70)
    print("七、数据驱动的取象修订建议")
    print("=" * 70)
    revision = {}
    for sym in ETF_SYMBOLS:
        name = ETF_NAMES[sym]
        guess = ETF_WUXING_GUESS.get(sym, [])
        tg_stats = group_stats(tian_gan_pct.get(sym, {}))
        dz_stats = group_stats(di_zhi_pct.get(sym, {}))
        tg_wx_scores, dz_wx_scores = {}, {}

        for k, v in tg_stats.items():
            wx = TIANGAN_WUXING.get(k, "")
            if wx:
                tg_wx_scores[wx] = tg_wx_scores.get(wx, 0) + v["avgPct"] * v["count"]
        for k, v in dz_stats.items():
            wx = DIZHI_WUXING.get(k, "")
            if wx:
                dz_wx_scores[wx] = dz_wx_scores.get(wx, 0) + v["avgPct"] * v["count"]

        all_wx = {}
        for wx in ["木", "火", "土", "金", "水"]:
            all_wx[wx] = tg_wx_scores.get(wx, 0) + dz_wx_scores.get(wx, 0)

        best_wx = sorted(all_wx.items(), key=lambda x: -x[1])
        suggested = [wx for wx, sc in best_wx if sc > 0][:2]
        if not suggested:
            suggested = [best_wx[0][0]]

        current = set(guess)
        new = set(suggested)
        match = "✓" if current == new else f"建议: {'/'.join(suggested)}"
        print(f"  {name}: 初拟={'/'.join(guess)} → {match}")
        revision[sym] = {"current": guess, "suggested": suggested, "scores": {wx: round(s, 4) for wx, s in best_wx}}

    outdir = os.path.join(ROOT, "data", "astro", "backtest")
    os.makedirs(outdir, exist_ok=True)
    out = {
        "range": {"start": RANGE_START, "end": RANGE_END},
        "calendarDays": len(all_days),
        "tradingDaysInRange": len(in_range_tds),
        "currentYearGanzhi": CURRENT_YEAR_GANZHI,
        "etfWuxingRevision": revision,
        "tianGanDetail": {sym: group_stats(tian_gan_pct.get(sym, {})) for sym in ETF_SYMBOLS},
        "tripleDetail": {sym: group_stats(triple_pct.get(sym, {})) for sym in ETF_SYMBOLS},
        "monthGanzhiDetail": {sym: {k: stat(v) for k, v in (month_ganzhi_pct.get(sym, {}) or {}).items()} for sym in ETF_SYMBOLS},
        "crashDays": crash_days,
    }
    outpath = os.path.join(outdir, "ganzhi_stats.json")
    with open(outpath, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n落盘: {outpath}")


if __name__ == "__main__":
    main()
