"""天时盘后校准 — 数据驱动：加权胜率预测 + 日柱切换。

流程（每日收盘后运行）：
  1. 读 astro_dynamic_vars.json 的日柱候选集
  2. 读 astro_calendar.jsonl 天时缓存 + data/index/daily 实际涨跌
  3. 对每个候选日柱，用全量历史统计特征胜率，滚动窗口算命中率
  4. 若某候选显著优于主日柱则切换
  5. 落盘校准报告 data/astro/calibration/YYYY-MM-DD.json
  6. 回写 astro_dynamic_vars.json 的 pillar

用法：python3 treasolo/m1_daily_calibrate.py [--day 2026-07-29]
"""
import argparse
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ = ZoneInfo("Asia/Shanghai")

VARS_PATH = os.path.join(ROOT, "八字", "astro_dynamic_vars.json")
CAL_PATH = os.path.join(ROOT, "data", "astro", "astro_calendar.jsonl")
HOLIDAYS_PATH = os.path.join(ROOT, "config", "holidays.json")
CAL_DIR = os.path.join(ROOT, "data", "astro", "calibration")

INDEX_DAILY = {
    "sh000001": os.path.join(ROOT, "data", "index", "daily", "sh000001", "daily.jsonl"),
    "sz399001": os.path.join(ROOT, "data", "index", "daily", "sz399001", "daily.jsonl"),
    "sz399006": os.path.join(ROOT, "data", "index", "daily", "sz399006", "daily.jsonl"),
    "sh000688": os.path.join(ROOT, "data", "index", "daily", "sh000688", "daily.jsonl"),
}


def load_vars():
    with open(VARS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_calendar_map():
    m = {}
    if os.path.exists(CAL_PATH):
        with open(CAL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("date"):
                        m[rec["date"]] = rec
                except Exception:
                    pass
    return m


def load_holidays():
    s = set()
    if os.path.exists(HOLIDAYS_PATH):
        try:
            obj = json.load(open(HOLIDAYS_PATH, "r", encoding="utf-8"))
            arr = obj if isinstance(obj, list) else obj.get("holidays", [])
            for d in arr:
                s.add(str(d))
        except Exception:
            pass
    return s


def load_index_pct_map():
    out = {}
    for code, fp in INDEX_DAILY.items():
        m = {}
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if rec.get("date") and rec.get("pct") is not None:
                            m[rec["date"]] = float(rec["pct"])
                    except Exception:
                        pass
        out[code] = m
    return out


# ---- 特征提取 ----
def relation_label(flow_wx, pillar_wx, sheng, ke):
    if not flow_wx or not pillar_wx:
        return None
    if flow_wx == pillar_wx:
        return "同气"
    if sheng.get(flow_wx) == pillar_wx:
        return "被生"
    if ke.get(flow_wx) == pillar_wx:
        return "被克"
    if sheng.get(pillar_wx) == flow_wx:
        return "泄"
    return "柱克"


def is_full_moon_window(moon_age):
    return 13 <= moon_age < 16.5


def is_new_moon_window(moon_age):
    return moon_age < 1.5 or moon_age >= 28


def phase_label(rec):
    a = float(rec.get("moonAge", 0) or 0)
    if is_full_moon_window(a):
        return "满月窗口"
    if is_new_moon_window(a):
        return "新月窗口"
    return "其他"


def calc_delivery_days(year, holidays):
    out = []
    for m in range(1, 13):
        first = date(year, m, 1)
        offset = (4 - first.weekday() + 7) % 7
        d = first + timedelta(days=offset + 14)
        while str(d) in holidays or d.weekday() >= 5:
            d = d + timedelta(days=1)
        out.append(str(d))
    return out


def risk_labels(rec, delivery_set):
    labels = []
    if rec.get("gzDay") == "丙午":
        labels.append("丙午日")
    if rec.get("tgWx") == "土" and rec.get("dzWx") == "土":
        labels.append("双土日")
    if rec.get("gzMonth") == "乙未":
        labels.append("乙未月")
    if rec.get("date") in delivery_set:
        labels.append("交割日")
    return labels


# ---- 特征胜率统计 + 加权预测 ----
def compute_feature_stats(code, pillar_tg, calendar_map, pct_map, delivery_set, static):
    """为指定日柱统计特征胜率，返回 features 表。"""
    sheng = static["sheng"]
    ke = static["ke"]
    tiangan_wuxing = static["tiangan_wuxing"]
    pillar_wx = tiangan_wuxing.get(pillar_tg, "")

    buckets = {"year_rel": {}, "month_rel": {}, "day_rel": {}, "phase": {}, "risk": {}}

    for d, pct in pct_map.get(code, {}).items():
        if pct == 0:
            continue
        rec = calendar_map.get(d)
        if not rec:
            continue
        wins = 1 if pct > 0 else 0

        def add(bucket, key):
            if key is None:
                return
            b = buckets[bucket]
            if key not in b:
                b[key] = {"wins": 0, "total": 0}
            b[key]["total"] += 1
            b[key]["wins"] += wins

        add("year_rel", relation_label(tiangan_wuxing.get(rec.get("ytg", ""), ""), pillar_wx, sheng, ke))
        add("month_rel", relation_label(tiangan_wuxing.get(rec.get("mtg", ""), ""), pillar_wx, sheng, ke))
        add("day_rel", relation_label(tiangan_wuxing.get(rec.get("tg", ""), ""), pillar_wx, sheng, ke))
        add("phase", phase_label(rec))
        for label in risk_labels(rec, delivery_set):
            add("risk", label)

    features = {}
    for bucket_name, b in buckets.items():
        features[bucket_name] = {}
        for key, v in b.items():
            n = v["total"]
            features[bucket_name][key] = {"win_rate": round(v["wins"] / n, 4) if n else 0.0, "n": n}
    return features


def predict_p_up(rec, pillar_tg, features, static, delivery_set):
    """加权胜率预测，返回看涨概率 p_up。"""
    sheng = static["sheng"]
    ke = static["ke"]
    tiangan_wuxing = static["tiangan_wuxing"]
    pillar_wx = tiangan_wuxing.get(pillar_tg, "")

    contribs = []

    def push(stat):
        if stat and stat.get("n", 0) >= 5:
            contribs.append(stat)

    push(features["year_rel"].get(relation_label(tiangan_wuxing.get(rec.get("ytg", ""), ""), pillar_wx, sheng, ke)))
    push(features["month_rel"].get(relation_label(tiangan_wuxing.get(rec.get("mtg", ""), ""), pillar_wx, sheng, ke)))
    push(features["day_rel"].get(relation_label(tiangan_wuxing.get(rec.get("tg", ""), ""), pillar_wx, sheng, ke)))
    push(features["phase"].get(phase_label(rec)))
    for label in risk_labels(rec, delivery_set):
        push(features["risk"].get(label))

    if not contribs:
        return 0.5
    num = sum(c["n"] * c["win_rate"] for c in contribs)
    den = sum(c["n"] for c in contribs)
    return num / den if den else 0.5


def direction(p_up):
    if p_up > 0.5:
        return "涨"
    if p_up < 0.5:
        return "跌"
    return "平"


def pct_direction(pct):
    if pct > 0:
        return "涨"
    if pct < 0:
        return "跌"
    return "平"


def rolling_hit_rate(code, pillar_tg, dates, calendar_map, pct_map, delivery_set, static):
    """滚动窗口内，用加权胜率预测的命中率。"""
    features = compute_feature_stats(code, pillar_tg, calendar_map, pct_map, delivery_set, static)
    hits = 0
    total = 0
    for d in dates:
        rec = calendar_map.get(d)
        pct = pct_map.get(code, {}).get(d)
        if not rec or pct is None or pct == 0:
            continue
        pred = direction(predict_p_up(rec, pillar_tg, features, static, delivery_set))
        if pred == "平":
            continue
        total += 1
        if (pred == "涨") == (pct > 0):
            hits += 1
    return (hits / total) if total else 0.0, total


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--day", default="")
    args = p.parse_args()

    dv = load_vars()
    static = dv["static"]
    calendar_map = load_calendar_map()
    holidays = load_holidays()
    index_pct_map = load_index_pct_map()

    # 各年份交割日
    years = {int(d[:4]) for d in calendar_map}
    delivery_set = set()
    for y in sorted(years):
        delivery_set.update(calc_delivery_days(y, holidays))

    day = str(args.day or "").strip()[:10]
    if not day:
        common = None
        for m in index_pct_map.values():
            if m:
                mx = max(m.keys())
                if common is None or mx < common:
                    common = mx
        day = common or ""
    if not day:
        print("无可用交易日数据")
        return 1

    all_dates = sorted(calendar_map.keys())
    dates_upto = [d for d in all_dates if d <= day]

    switch_rule = dv["tunable"].get("switch_rule", {})
    window = int(switch_rule.get("window", 20))
    min_samples = int(switch_rule.get("min_samples", 10))
    min_advantage = float(switch_rule.get("min_advantage", 0.15))
    recent_dates = dates_upto[-window:] if len(dates_upto) >= window else dates_upto

    report = {"day": day, "generatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
              "window": window, "min_samples": min_samples, "min_advantage": min_advantage,
              "indices": [], "switches": []}

    changed = False
    for idx in dv["tunable"]["indices"]:
        code = idx["code"]
        name = idx["name"]
        pillar = idx["pillar"]
        candidates = idx.get("candidates", [])

        # 各候选日柱滚动命中率
        cand_stats = {}
        for cand in candidates:
            hr, n = rolling_hit_rate(code, cand[0], recent_dates, calendar_map, index_pct_map, delivery_set, static)
            cand_stats[cand] = {"hit_rate": round(hr, 4), "samples": n}

        # 切换决策
        best = pillar
        best_hr = cand_stats.get(pillar, {}).get("hit_rate", 0.0)
        for cand in candidates:
            if cand == pillar:
                continue
            cs = cand_stats.get(cand, {})
            hr = cs.get("hit_rate", 0.0)
            n = cs.get("samples", 0)
            if n >= min_samples and hr - best_hr >= min_advantage:
                best = cand
                best_hr = hr

        if best != pillar:
            report["switches"].append({"code": code, "name": name, "from": pillar, "to": best,
                                       "reason": f"候选{best}命中率{best_hr:.0%} vs 主{pillar}"})
            idx["pillar"] = best
            changed = True

        report["indices"].append({
            "code": code, "name": name, "pillar": pillar, "candidate_stats": cand_stats,
            "pillar_switched": best if best != pillar else None,
        })

    os.makedirs(CAL_DIR, exist_ok=True)
    report_path = os.path.join(CAL_DIR, f"{day}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if changed:
        with open(VARS_PATH, "w", encoding="utf-8") as f:
            json.dump(dv, f, ensure_ascii=False, indent=2)
        print(f"已切换日柱并回写 {VARS_PATH}")
    else:
        print("无日柱切换")

    print(f"校准报告已写入 {report_path}")
    for s in report["switches"]:
        print("切换:", s["name"], s["from"], "->", s["to"], "|", s["reason"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
