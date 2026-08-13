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
TIANGAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}
DIZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

INDICES = {
    "sh000001": "上证", "sz399001": "深证",
    "sz399006": "创业", "sh000688": "科创",
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
    dz = jiazi[1] if len(jiazi) >= 2 else ""
    month_jiazi = scd.get_month().get_name()
    mtg = month_jiazi[0] if len(month_jiazi) >= 1 else ""
    phase_idx, _ = moon_phase_index(d)
    year_tg = CURRENT_YEAR_GANZHI[0]
    return {
        "date": f"{d.year:04d}-{d.month:02d}-{d.day:02d}",
        "sixtyCycleDay": jiazi, "tianGan": tg,
        "tianGanWx": TIANGAN_WUXING.get(tg, ""), "diZhi": dz,
        "diZhiWx": DIZHI_WUXING.get(dz, ""),
        "sixtyCycleMonth": month_jiazi,
        "monthTianGan": mtg, "monthTianGanWx": TIANGAN_WUXING.get(mtg, ""),
        "yearTianGan": year_tg, "yearTianGanWx": TIANGAN_WUXING.get(year_tg, ""),
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


def pearson_r(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0, 0
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


def main():
    start = date.fromisoformat(RANGE_START)
    end = date.fromisoformat(RANGE_END)

    print("=" * 80)
    print("多周期干支信号合成器")
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

    print(f"\n  训练数据: {RANGE_START} ~ {RANGE_END}（{len(in_range_tds)}个交易日）")
    print(f"  流年: {CURRENT_YEAR_GANZHI}")

    print()
    print("=" * 80)
    print("一、单层得分矩阵训练（ETF × 10天干）")
    print("=" * 80)

    day_score = {sym: {} for sym in ETF_SYMBOLS}
    day_score_raw = {sym: defaultdict(list) for sym in ETF_SYMBOLS}
    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        if not tg:
            continue
        for sym in ETF_SYMBOLS:
            r = records[sym].get(td)
            if r:
                day_score_raw[sym][tg].append(r["pct"])

    for sym in ETF_SYMBOLS:
        for tg in TIANGAN:
            arr = day_score_raw[sym].get(tg, [])
            if arr:
                day_score[sym][tg] = round(sum(arr) / len(arr), 4)
            else:
                day_score[sym][tg] = 0.0

    print(f"\n  {'ETF':<10s}", end="")
    for tg in TIANGAN:
        print(f"  {tg}({TIANGAN_WUXING.get(tg,'?')}):>8s", end="")
    print()
    for sym in ETF_SYMBOLS:
        name = ETF_NAMES.get(sym, sym)
        print(f"  {cjk_pad(name):<10s}", end="")
        for tg in TIANGAN:
            v = day_score[sym][tg]
            print(f"  {v:>+8.2f}", end="")
        print()

    print()
    print("=" * 80)
    print("二、日干×月干 交互得分")
    print("=" * 80)

    interaction_dm = {sym: defaultdict(list) for sym in ETF_SYMBOLS}
    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        mtg = astro.get("monthTianGan", "")
        if not tg or not mtg:
            continue
        key = f"{mtg}{tg}"
        for sym in ETF_SYMBOLS:
            r = records[sym].get(td)
            if r:
                interaction_dm[sym][key].append(r["pct"])

    dm_score = {sym: {} for sym in ETF_SYMBOLS}
    for sym in ETF_SYMBOLS:
        for key, arr in interaction_dm[sym].items():
            if len(arr) >= 3:
                dm_score[sym][key] = round(sum(arr) / len(arr), 2)

    for sym in ETF_SYMBOLS[:4]:
        name = ETF_NAMES.get(sym, sym)
        significant = [(k, v) for k, v in dm_score[sym].items() if abs(v) >= 0.8]
        if significant:
            significant.sort(key=lambda x: -x[1])
            print(f"\n  【{name}】 显著交互 (|avg|>=0.8%):")
            for k, v in significant[:8]:
                mtg = k[0]; tg_wx = TIANGAN_WUXING.get(k[1], "?")
                mwx = TIANGAN_WUXING.get(mtg, "?")
                print(f"    月{mtg}({mwx})×日{k[1]}({tg_wx}): avg {v:+.2f}%")

    print()
    print("=" * 80)
    print("三、日干×年干 交互得分 (年=乙木)")
    print("=" * 80)

    interaction_dy = {sym: defaultdict(list) for sym in ETF_SYMBOLS}
    for td in in_range_tds:
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        ytg = astro.get("yearTianGan", "")
        if not tg or not ytg:
            continue
        key = f"{ytg}{tg}"
        for sym in ETF_SYMBOLS:
            r = records[sym].get(td)
            if r:
                interaction_dy[sym][key].append(r["pct"])

    dy_score = {sym: {} for sym in ETF_SYMBOLS}
    for sym in ETF_SYMBOLS:
        for key, arr in interaction_dy[sym].items():
            if len(arr) >= 3:
                dy_score[sym][key] = round(sum(arr) / len(arr), 2)

    for sym in ETF_SYMBOLS[:4]:
        name = ETF_NAMES.get(sym, sym)
        print(f"  {cjk_pad(name)}: ", end="")
        items = [(k, v) for k, v in sorted(dy_score[sym].items(), key=lambda x: -x[1])]
        for k, v in items[:4]:
            dtg = k[1]
            print(f"年乙×日{dtg}({TIANGAN_WUXING.get(dtg,'?')})={v:+.2f}  ", end="")
        print()

    print()
    print("=" * 80)
    print("四、权重训练（相关性优化）")
    print("=" * 80)

    signals = {sym: [] for sym in ETF_SYMBOLS}
    actuals = {sym: [] for sym in ETF_SYMBOLS}

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
            signals[sym].append((s1, s2, s3))
            actuals[sym].append(r["pct"])

    weights = {}
    for sym in ETF_SYMBOLS:
        best_r = -2
        best_w = (1.0, 0.2, 0.1)
        for w1 in [0.5, 1.0, 1.5, 2.0]:
            for w2 in [0.0, 0.1, 0.2, 0.3, 0.5]:
                for w3 in [0.0, 0.05, 0.1, 0.2]:
                    preds = [w1 * s[0] + w2 * s[1] + w3 * s[2] for s in signals[sym]]
                    r, n = pearson_r(preds, actuals[sym])
                    if r > best_r:
                        best_r = r
                        best_w = (w1, w2, w3)
        weights[sym] = {"w1": best_w[0], "w2": best_w[1], "w3": best_w[2], "r": best_r}

    print(f"\n  {'ETF':<10s} {'W1(日干)':>8s} {'W2(月交)':>8s} {'W3(年交)':>8s} {'r':>8s}")
    print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for sym in ETF_SYMBOLS:
        w = weights[sym]
        print(f"  {cjk_pad(ETF_NAMES.get(sym,sym)):<10s} {w['w1']:>8.2f} {w['w2']:>8.2f} {w['w3']:>8.2f} {w['r']:>+8.3f}")

    print()
    print("=" * 80)
    print("五、当前信号（最近7天滚动预测）")
    print("=" * 80)

    today = date.today()
    predict_dates = []
    for td in reversed(in_range_tds):
        if len(predict_dates) >= 10:
            break
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        if tg:
            predict_dates.append(td)
    predict_dates.sort()

    for td in predict_dates[-7:]:
        astro = date_to_astro.get(td, {})
        tg = astro.get("tianGan", "")
        mtg = astro.get("monthTianGan", "")
        ytg = astro.get("yearTianGan", "")
        ph = astro.get("phaseName", "")
        mgz = astro.get("sixtyCycleMonth", "")

        print(f"\n  {td} {astro.get('sixtyCycleDay','')}日 {ph} [{mgz}]")
        print(f"    能量: 年{ytg}({TIANGAN_WUXING.get(ytg,'?')}) "
              f"月{mtg}({TIANGAN_WUXING.get(mtg,'?')}) "
              f"日{tg}({TIANGAN_WUXING.get(tg,'?')})")
        print(f"  {'ETF':<10s} {'信号':>8s} {'倾向':>6s} {'实际':>8s}")
        print(f"  {'-'*10} {'-'*8} {'-'*6} {'-'*8}")

        signals_today = []
        for sym in ETF_SYMBOLS:
            w = weights[sym]
            s1 = day_score[sym].get(tg, 0)
            s2 = dm_score[sym].get(f"{mtg}{tg}", 0)
            s3 = dy_score[sym].get(f"{ytg}{tg}", 0)
            sig = w["w1"] * s1 + w["w2"] * s2 + w["w3"] * s3
            actual = records[sym].get(td, {}).get("pct")
            bar_act = "+" if (actual or 0) >= 0 else ""

            stars = ""
            if sig >= 0.8:
                stars = "★★★"
            elif sig >= 0.4:
                stars = "★★"
            elif sig >= 0.15:
                stars = "★"
            elif sig <= -0.8:
                stars = "☆☆☆"
            elif sig <= -0.4:
                stars = "☆☆"
            elif sig <= -0.15:
                stars = "☆"

            bias = "看多" if sig > 0.1 else ("看空" if sig < -0.1 else "中性")
            actual_s = f"{bar_act}{actual:.2f}%" if actual is not None else "-"

            print(f"  {cjk_pad(ETF_NAMES.get(sym,sym)):<10s} {sig:>+8.2f} {stars:>6s} {bias:>6s} {actual_s:>8s}")
            signals_today.append({"sym": sym, "name": ETF_NAMES.get(sym, sym), "signal": round(sig, 2), "stars": stars, "bias": bias, "actual": actual})

    print()
    print("=" * 80)
    print("六、信号质量评估")
    print("=" * 80)

    all_preds = []
    all_actuals = []
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
            if r is not None:
                all_preds.append(sig)
                all_actuals.append(r["pct"])

    overall_r, n = pearson_r(all_preds, all_actuals)
    print(f"  全样本相关系数 r = {overall_r:+.4f}（n={n}）")

    correct = sum(1 for i in range(n) if (all_preds[i] > 0 and all_actuals[i] > 0) or (all_preds[i] < 0 and all_actuals[i] < 0))
    total_nonzero = sum(1 for i in range(n) if all_preds[i] != 0 and all_actuals[i] != 0)
    if total_nonzero > 0:
        print(f"  方向正确率 = {correct}/{total_nonzero} = {correct/total_nonzero:.1%}")

    strong = [(all_preds[i], all_actuals[i]) for i in range(n) if abs(all_preds[i]) >= 0.5]
    if strong:
        strong_correct = sum(1 for p, a in strong if (p > 0 and a > 0) or (p < 0 and a < 0))
        print(f"  强信号(|信号|>=0.5)方向正确率 = {strong_correct}/{len(strong)} = {strong_correct/len(strong):.1%}")

    outdir = os.path.join(ROOT, "data", "astro", "backtest")
    os.makedirs(outdir, exist_ok=True)
    out = {
        "range": {"start": RANGE_START, "end": RANGE_END},
        "dayScore": day_score,
        "dmScore": {sym: dm_score.get(sym, {}) for sym in ETF_SYMBOLS},
        "dyScore": {sym: dy_score.get(sym, {}) for sym in ETF_SYMBOLS},
        "weights": weights,
        "overallR": overall_r,
        "directionAccuracy": round(correct / total_nonzero, 4) if total_nonzero > 0 else 0,
    }
    with open(os.path.join(outdir, "signal_synthesizer.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n落盘: {os.path.join(outdir, 'signal_synthesizer.json')}")


if __name__ == "__main__":
    main()
