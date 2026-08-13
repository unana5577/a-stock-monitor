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
    "sh000001": "上证指数", "sz399001": "深证成指",
    "sz399006": "创业板指", "sh000688": "科创50",
}

TIANGAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
DIZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

RANGE_START = "2025-05-01"
RANGE_END = "2026-06-13"


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
        "sixtyCycleDay": jiazi, "tianGan": tg, "tianGanWx": TIANGAN_WUXING.get(tg, ""),
        "diZhi": dz, "diZhiWx": DIZHI_WUXING.get(dz, ""),
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


def cjk_pad(s, width=6):
    w = sum(2 if ord(c) > 127 else 1 for c in s)
    return s + " " * max(0, width + 6 - w)


def main():
    start = date.fromisoformat(RANGE_START)
    end = date.fromisoformat(RANGE_END)

    print("=" * 80)
    print("月相周期逐次分析 — 满月→满月完整周期")
    print("=" * 80)

    all_days = []
    cur = start
    while cur <= end:
        all_days.append(day_astro(cur))
        cur = cur + timedelta(days=1)
    date_to_astro = {d["date"]: d for d in all_days}

    index_data = {}
    for code in INDICES:
        index_data[code] = load_daily(code)

    trading_dates = set()
    for recs in index_data.values():
        trading_dates.update(recs.keys())
    trading_dates = sorted(trading_dates)
    in_range_tds = [td for td in trading_dates if RANGE_START <= td <= RANGE_END]

    full_moon_dates = sorted([
        td for td in in_range_tds
        if date_to_astro.get(td, {}).get("phaseIndex") == 4
    ])

    cycles = []
    for i in range(len(full_moon_dates) - 1):
        fm_start = full_moon_dates[i]
        fm_end = full_moon_dates[i + 1]
        cycle_tds = [td for td in in_range_tds if fm_start <= td < fm_end]
        if len(cycle_tds) >= 5:
            cycles.append({"start": fm_start, "end": fm_end, "dates": cycle_tds})

    print(f"  测试区间: {RANGE_START} ~ {RANGE_END}")
    print(f"  满月日: {len(full_moon_dates)} 次")
    print(f"  完整周期: {len(cycles)} 个\n")

    all_cycles_output = []

    for idx_cycle, cyc in enumerate(cycles, 1):
        cyc_start = cyc["start"]
        cyc_end = cyc["end"]
        tds = cyc["dates"]

        nd_start = date.fromisoformat(cyc_start)
        nd_end = date.fromisoformat(cyc_end)
        duration = (nd_end - nd_start).days

        print(f"{'─' * 80}")
        print(f"第{idx_cycle}周期: {cyc_start}(满月) → {cyc_end}(满月)")
        print(f"{'─' * 80}")
        print(f"  时间跨度: {duration}天  交易日: {len(tds)}天")
        astro_start = date_to_astro.get(cyc_start, {})
        astro_end = date_to_astro.get(cyc_end, {})
        print(f"  起始: {astro_start.get('sixtyCycleDay','')}日({astro_start.get('tianGanWx','')}) {astro_start.get('lunarMonth','')}{astro_start.get('lunarDay','')}")
        print(f"  结束: {astro_end.get('sixtyCycleDay','')}日({astro_end.get('tianGanWx','')}) {astro_end.get('lunarMonth','')}{astro_end.get('lunarDay','')}")

        daily_records = {code: {} for code in INDICES}
        for td in tds:
            for code in INDICES:
                r = index_data[code].get(td)
                if r is not None:
                    daily_records[code][td] = r

        print()
        print(f"  {'日期':　<14s} {'干支':<6s} {'月相':<6s}", end="")
        for code, name in INDICES.items():
            print(f"  {cjk_pad(name):>10s}", end="")
        print()

        for td in tds:
            astro = date_to_astro.get(td, {})
            gz = astro.get("sixtyCycleDay", "")
            ph = astro.get("phaseName", "")
            print(f"  {td:<14s} {gz:<6s} {ph:<6s}", end="")
            for code in INDICES:
                r = daily_records[code].get(td)
                if r:
                    bar = "+" if r["pct"] >= 0 else ""
                    color_tag = ""
                    if r["pct"] >= 2.0:
                        color_tag = " ↑↑"
                    elif r["pct"] >= 1.0:
                        color_tag = " ↑"
                    elif r["pct"] <= -2.0:
                        color_tag = " ↓↓"
                    elif r["pct"] <= -1.0:
                        color_tag = " ↓"
                    print(f"  {bar}{r['pct']:>7.2f}%{color_tag}", end="")
                else:
                    print(f"  {'-':>8s}", end="")
            print()

        print()
        cumul = {}
        for code in INDICES:
            vals = [daily_records[code][td]["pct"] for td in tds if td in daily_records[code]]
            cumul_ret = 1.0
            for v in vals:
                cumul_ret *= (1 + v / 100)
            cumul_ret = round((cumul_ret - 1) * 100, 2)
            cumul[code] = cumul_ret

            wins = sum(1 for v in vals if v > 0)
            strongest_td = max(tds, key=lambda d: daily_records[code].get(d, {}).get("pct", -999)) if vals else ""
            weakest_td = min(tds, key=lambda d: daily_records[code].get(d, {}).get("pct", 999)) if vals else ""
            sp = daily_records[code].get(strongest_td, {}).get("pct", 0) if strongest_td else 0
            wp = daily_records[code].get(weakest_td, {}).get("pct", 0) if weakest_td else 0

            bar = "+" if cumul_ret >= 0 else ""
            print(f"  {cjk_pad(INDICES[code])} 累积 {bar}{cumul_ret:.2f}%  "
                  f"胜率 {wins}/{len(vals)}  "
                  f"最强({strongest_td} {bar}{sp:.2f}%)  "
                  f"最弱({weakest_td} {wp:.2f}%)")

        print()

        all_cycles_output.append({
            "cycle": idx_cycle, "start": cyc_start, "end": cyc_end,
            "tradingDays": len(tds), "durationDays": duration,
            "cumulative": cumul,
            "startGanzhi": astro_start.get("sixtyCycleDay", ""),
            "endGanzhi": astro_end.get("sixtyCycleDay", ""),
        })

    print("=" * 80)
    print("周期汇总")
    print("=" * 80)
    print(f"  {'周期':<8s} {'起止日期':<26s} {'上证累积':>10s} {'深证累积':>10s} {'创业累积':>10s} {'科创累积':>10s}")
    print(f"  {'-'*8} {'-'*26} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for c in all_cycles_output:
        print(f"  {c['cycle']:<8d} {c['start']}~{c['end']:<10s}  "
              f"{c['cumulative']['sh000001']:>+8.2f}%  "
              f"{c['cumulative']['sz399001']:>+8.2f}%  "
              f"{c['cumulative']['sz399006']:>+8.2f}%  "
              f"{c['cumulative']['sh000688']:>+8.2f}%")

    outdir = os.path.join(ROOT, "data", "astro", "backtest")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "cycle_report.json"), "w") as f:
        json.dump(all_cycles_output, f, ensure_ascii=False, indent=2)
    print(f"\n落盘: {os.path.join(outdir, 'cycle_report.json')}")


if __name__ == "__main__":
    main()
