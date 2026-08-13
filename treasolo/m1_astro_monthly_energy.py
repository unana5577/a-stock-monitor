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

TIANGAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
DIZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

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
    month_jiazi = scd.get_month().get_name()
    mtg = month_jiazi[0] if len(month_jiazi) >= 1 else ""
    mdz = month_jiazi[1] if len(month_jiazi) >= 2 else ""
    phase_idx, _ = moon_phase_index(d)
    return {
        "date": f"{d.year:04d}-{d.month:02d}-{d.day:02d}",
        "sixtyCycleDay": jiazi, "tianGan": tg,
        "tianGanWx": TIANGAN_WUXING.get(tg, ""),
        "sixtyCycleMonth": month_jiazi,
        "monthTianGan": mtg, "monthTianGanWx": TIANGAN_WUXING.get(mtg, ""),
        "monthDiZhi": mdz, "monthDiZhiWx": DIZHI_WUXING.get(mdz, ""),
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
        return {"avgPct": 0, "winRate": 0, "count": 0}
    n = len(arr)
    avg = sum(arr) / n
    return {"count": n, "avgPct": round(avg, 4), "winRate": round(sum(1 for v in arr if v > 0) / n, 4)}


def cjk_pad(s, width=6):
    w = sum(2 if ord(c) > 127 else 1 for c in s)
    return s + " " * max(0, width + 4 - w)


def wuxing_signature(ganzhi_str):
    tg = ganzhi_str[0] if len(ganzhi_str) >= 1 else "?"
    dz = ganzhi_str[1] if len(ganzhi_str) >= 2 else "?"
    return f"{TIANGAN_WUXING.get(tg, '?')}{DIZHI_WUXING.get(dz, '?')}"


def wuxing_bias(ganzhi_str):
    tg = ganzhi_str[0] if len(ganzhi_str) >= 1 else ""
    tg_wx = TIANGAN_WUXING.get(tg, "")
    dz = ganzhi_str[1] if len(ganzhi_str) >= 2 else ""
    dz_wx = DIZHI_WUXING.get(dz, "")
    wx_count = defaultdict(int)
    wx_count[tg_wx] += 2
    wx_count[dz_wx] += 1
    return [(w, c) for w, c in sorted(wx_count.items(), key=lambda x: -x[1]) if w]


def main():
    start = date.fromisoformat(RANGE_START)
    end = date.fromisoformat(RANGE_END)

    print("=" * 80)
    print(f"流年流月能量画像 — {CURRENT_YEAR_GANZHI}年")
    print("=" * 80)

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

    year_tg = CURRENT_YEAR_GANZHI[0]
    year_dz = CURRENT_YEAR_GANZHI[1]
    year_wx = wuxing_signature(CURRENT_YEAR_GANZHI)
    year_bias = wuxing_bias(CURRENT_YEAR_GANZHI)

    print(f"\n  流年: {CURRENT_YEAR_GANZHI}（{year_wx}）")
    print(f"  年干{year_tg}({TIANGAN_WUXING.get(year_tg,'?')}) 年支{year_dz}({DIZHI_WUXING.get(year_dz,'?')})")

    month_order = []
    seen = set()
    for td in sorted(trading_dates):
        mgz = date_to_astro.get(td, {}).get("sixtyCycleMonth", "")
        if mgz and mgz not in seen:
            seen.add(mgz)
            month_order.append(mgz)

    month_pct_idx = defaultdict(lambda: {code: [] for code in INDICES})
    month_pct_etf = defaultdict(lambda: defaultdict(list))
    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        mgz = astro.get("sixtyCycleMonth", "")
        if not mgz:
            continue
        for code in INDICES:
            r = records[code].get(td)
            if r:
                month_pct_idx[mgz][code].append(r["pct"])
        for sym in ETF_SYMBOLS:
            r = records[sym].get(td)
            if r:
                month_pct_etf[mgz][sym].append(r["pct"])

    monthly_report = []

    for mgz in month_order[:14]:
        mgz_tg = mgz[0] if len(mgz) >= 1 else ""
        mgz_dz = mgz[1] if len(mgz) >= 2 else ""
        mgz_wx = wuxing_signature(mgz)
        mgz_bias = wuxing_bias(mgz)

        idx_stats = {code: stat(month_pct_idx[mgz][code]) for code in INDICES}
        etf_stats = {sym: stat(arr) for sym, arr in month_pct_etf[mgz].items() if arr}

        print()
        print(f"{'─' * 80}")
        print(f"【{mgz}】月干{mgz_tg}({TIANGAN_WUXING.get(mgz_tg,'?')}) 月支{mgz_dz}({DIZHI_WUXING.get(mgz_dz,'?')})")
        print(f"{'─' * 80}")

        combined_bias = defaultdict(int)
        for w, c in year_bias:
            combined_bias[w] += c
        for w, c in mgz_bias:
            combined_bias[w] += c

        strong_wx = sorted(combined_bias.items(), key=lambda x: -x[1])
        wx_desc = " > ".join(f"{w}({c})" for w, c in strong_wx if c >= 3)
        print(f"  流年+流月能量倾斜: {wx_desc}")
        print()

        print(f"  4大盘表现:")
        for code, name in INDICES.items():
            s = idx_stats[code]
            bar = "+" if s["avgPct"] >= 0 else ""
            tag = " ★" if s["avgPct"] >= 1.0 else (" ▼" if s["avgPct"] <= -0.5 else "")
            print(f"    {cjk_pad(name)} avg {bar}{s['avgPct']:.2f}%  "
                  f"win {s['winRate']:.0%}  n={s['count']}{tag}")
        print()

        strong_etfs = []
        weak_etfs = []
        for sym, s in sorted(etf_stats.items(), key=lambda x: -x[1]["avgPct"]):
            if s["avgPct"] >= 0.5 and s["count"] >= 5:
                strong_etfs.append((sym, s))
            elif s["avgPct"] <= -0.3 and s["count"] >= 5:
                weak_etfs.append((sym, s))

        if strong_etfs:
            print(f"  ★ 利好ETF:")
            for sym, s in strong_etfs:
                print(f"    {cjk_pad(ETF_NAMES.get(sym,sym))} avg +{s['avgPct']:.2f}%  "
                      f"win {s['winRate']:.0%}  n={s['count']}")

        if weak_etfs:
            print(f"  ☆ 不利ETF:")
            for sym, s in weak_etfs:
                print(f"    {cjk_pad(ETF_NAMES.get(sym,sym))} avg {s['avgPct']:.2f}%  "
                      f"win {s['winRate']:.0%}  n={s['count']}")

        by_wx = defaultdict(list)
        for sym, s in etf_stats.items():
            if s["count"] >= 3:
                for w, _ in year_bias:
                    by_wx[w].append((sym, s["avgPct"]))

        monthly_report.append({
            "monthGanzhi": mgz, "wuxing": mgz_wx,
            "energyTilt": strong_wx[:3],
            "indices": idx_stats,
            "strongEtfs": [{"sym": s, "name": ETF_NAMES.get(s, s), "avgPct": v["avgPct"]} for s, v in strong_etfs],
            "weakEtfs": [{"sym": s, "name": ETF_NAMES.get(s, s), "avgPct": v["avgPct"]} for s, v in weak_etfs],
        })

    print()
    print("=" * 80)
    print("年度汇总: 各月利好ETF一览")
    print("=" * 80)
    print(f"  {'月份':<8s} {'干支':<6s} {'五行':<8s} {'利好ETF':<50s}")
    print(f"  {'-'*8} {'-'*6} {'-'*8} {'-'*50}")
    for r in monthly_report:
        strong_names = ", ".join(f"{x['name']}({x['avgPct']:+.1f}%)" for x in r["strongEtfs"][:4])
        if not strong_names:
            strong_names = "(无显著利好)"
        print(f"  {r['monthGanzhi']:<8s} {r['monthGanzhi']:<6s} {r['wuxing']:<8s} {strong_names}")

    outdir = os.path.join(ROOT, "data", "astro", "backtest")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "monthly_energy.json"), "w") as f:
        json.dump({"currentYearGanzhi": CURRENT_YEAR_GANZHI, "months": monthly_report}, f, ensure_ascii=False, indent=2)
    print(f"\n落盘: {os.path.join(outdir, 'monthly_energy.json')}")


if __name__ == "__main__":
    main()
