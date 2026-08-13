"""天时特征胜率统计 — 数据驱动的涨跌概率基础。

对每个指数的主日柱，统计各「特征取值」的历史涨跌胜率：
  - year_rel / month_rel / day_rel：年/月/日干 vs 日柱天干的生克关系（同气/被生/被克/泄/柱克）
  - phase：满月窗口 / 新月窗口 / 其他
  - risk：丙午日 / 双土日 / 乙未月 / 交割日

输出 八字/feature_stats.json，供 server/api/astro.js 做加权胜率预测。

用法：python3 treasolo/m1_astro_feature_stats.py
"""
import json
import os
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VARS_PATH = os.path.join(ROOT, "八字", "astro_dynamic_vars.json")
CAL_PATH = os.path.join(ROOT, "data", "astro", "astro_calendar.jsonl")
HOLIDAYS_PATH = os.path.join(ROOT, "config", "holidays.json")
OUT_PATH = os.path.join(ROOT, "八字", "feature_stats.json")

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


def relation(flow_wx, pillar_wx, sheng, ke):
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


def calc_delivery_days(year, holidays):
    out = []
    for m in range(1, 13):
        first = date(year, m, 1)
        first_dow = first.weekday()  # 0=周一
        offset = (4 - first_dow + 7) % 7  # 到第一个周五
        d = first + timedelta(days=offset + 14)  # 第三个周五
        while str(d) in holidays or d.weekday() >= 5:
            d = d + timedelta(days=1)
        out.append(str(d))
    return out


def phase_label(rec):
    a = float(rec.get("moonAge", 0) or 0)
    if is_full_moon_window(a):
        return "满月窗口"
    if is_new_moon_window(a):
        return "新月窗口"
    return "其他"


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


def add_stat(bucket, key, pct):
    if key is None:
        return
    if key not in bucket:
        bucket[key] = {"wins": 0, "total": 0}
    bucket[key]["total"] += 1
    if pct > 0:
        bucket[key]["wins"] += 1


def finalize(bucket):
    out = {}
    for key, v in bucket.items():
        n = v["total"]
        out[key] = {"win_rate": round(v["wins"] / n, 4) if n else 0.0, "n": n}
    return out


def main():
    dv = load_vars()
    static = dv["static"]
    sheng = static["sheng"]
    ke = static["ke"]
    tiangan_wuxing = static["tiangan_wuxing"]
    indices = dv["tunable"]["indices"]

    calendar_map = load_calendar_map()
    holidays = load_holidays()
    pct_map = load_index_pct_map()

    # 各年份交割日
    years = set()
    for d in calendar_map:
        years.add(int(d[:4]))
    delivery_set = set()
    for y in sorted(years):
        delivery_set.update(calc_delivery_days(y, holidays))

    result = {
        "version": 1,
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "indices": {},
    }

    for idx in indices:
        code = idx["code"]
        name = idx["name"]
        pillar = idx["pillar"]
        pillar_tg = pillar[0] if pillar else ""
        pillar_wx = tiangan_wuxing.get(pillar_tg, "")

        pcts = pct_map.get(code, {})
        buckets = {
            "year_rel": {},
            "month_rel": {},
            "day_rel": {},
            "phase": {},
            "risk": {},
        }

        for d, pct in pcts.items():
            if pct == 0:
                continue
            rec = calendar_map.get(d)
            if not rec:
                continue

            ytg = rec.get("ytg", "")
            mtg = rec.get("mtg", "")
            tg = rec.get("tg", "")

            add_stat(buckets["year_rel"],
                     relation(tiangan_wuxing.get(ytg, ""), pillar_wx, sheng, ke), pct)
            add_stat(buckets["month_rel"],
                     relation(tiangan_wuxing.get(mtg, ""), pillar_wx, sheng, ke), pct)
            add_stat(buckets["day_rel"],
                     relation(tiangan_wuxing.get(tg, ""), pillar_wx, sheng, ke), pct)
            add_stat(buckets["phase"], phase_label(rec), pct)
            for label in risk_labels(rec, delivery_set):
                add_stat(buckets["risk"], label, pct)

        result["indices"][code] = {
            "name": name,
            "pillar": pillar,
            "candidates": idx.get("candidates", []),
            "features": {k: finalize(v) for k, v in buckets.items()},
        }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"落盘: {OUT_PATH}")

    # 简要打印
    for code, info in result["indices"].items():
        feats = info["features"]
        risk = feats["risk"]
        print(f"\n{info['name']}({info['pillar']}):")
        for label, v in sorted(risk.items(), key=lambda x: -(x[1]["n"])):
            print(f"  {label}: 胜率 {v['win_rate']:.0%} n={v['n']}")
        for rel_type in ["year_rel", "month_rel", "day_rel"]:
            rel = feats[rel_type]
            line = "  " + rel_type + ": " + ", ".join(
                f"{k}={v['win_rate']:.0%}({v['n']})" for k, v in sorted(rel.items(), key=lambda x: -x[1]["n"])
            )
            print(line)


if __name__ == "__main__":
    main()
