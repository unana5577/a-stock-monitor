"""
ETF回调深度分析 → sector-proxy.json 个性化挂单档位
=====================================================
复用 backtest_pullback_entry 的回调发现逻辑
"""
import json, os, sys, math

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, DIR)
from stage_detector import detect_stage, calc_ma, STAGE_UPTREND, STAGE_DEFENSE

FROM_DATE = "2025-05-01"
ETF_SYMS = ["sh512480","sh512400","sh515880","sh516010","sh516510","sh562500","sh563530","sh515120","sh516160","sh562590"]


def find_pullback_devs(rows):
    """找每个主升段中独立回调事件的 MA20 偏离"""
    closes = [r["close"] for r in rows]
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)

    devs = []
    i = 0
    while i < len(rows):
        if rows[i]["date"] < FROM_DATE:
            i += 1; continue
        stage, _ = detect_stage(rows, i)
        if stage != STAGE_UPTREND:
            i += 1; continue

        ut_start = i
        i += 1
        while i < len(rows):
            s, _ = detect_stage(rows, i)
            if s == STAGE_UPTREND:
                i += 1; continue
            if s == STAGE_DEFENSE:
                break
            pb_start = i
            low_idx = i; low_p = closes[i]
            i += 1
            while i < len(rows):
                s, _ = detect_stage(rows, i)
                if s in (STAGE_UPTREND, STAGE_DEFENSE):
                    break
                if closes[i] < low_p:
                    low_idx = i; low_p = closes[i]
                i += 1

            m20 = ma20[low_idx]; m60 = ma60[low_idx]
            if m20 and m60 and low_p > m60:
                devs.append((low_p - m20) / m20 * 100)

            if s == STAGE_DEFENSE:
                i += 1; break
        i += 1

    return devs, ma20[-1] if ma20[-1] else None


def compute_tiers(deviations, current_ma20):
    """根据回调深度分位生成档位"""
    n = len(deviations)
    if n < 2:
        return [
            {"pct": 50, "price": round(current_ma20, 3), "label": "MA20"},
            {"pct": 50, "price": round(current_ma20 * 0.95, 3), "label": "MA20-5%"},
        ]

    devs_sorted = sorted(deviations)
    p10 = devs_sorted[max(0, int(n * 0.10))]
    p25 = devs_sorted[max(0, int(n * 0.25))]
    p50 = devs_sorted[max(0, int(n * 0.50))]
    p75 = devs_sorted[max(0, int(n * 0.75))]

    # 档位1: 在 p50 附近 — 一半回调打到这里
    # 档位2: 在 p25 附近 — 只有 25% 回调更深
    # 未触发深度: tier2 确保 80%+ 回调能被覆盖

    # 浅回调型: 大部分在MA20上方, 紧凑间距
    if p50 > 1.0:
        t1_off = max(min(p50, 1.0), -2.0)
        t2_off = min(p25, -2.0)
    # 中等
    elif p50 > -2.0:
        t1_off = max(p50, -3.0)
        t2_off = min(p25, -5.0)
    # 深回调型
    else:
        t1_off = min(p50, -3.0)
        t2_off = min(p25, -7.0)

    t1_label = f"MA20{('+' if t1_off >= 0 else '')}{t1_off:.0f}%"
    t2_label = f"MA20{('+' if t2_off >= 0 else '')}{t2_off:.0f}%"

    return [
        {"pct": 30, "price": round(current_ma20 * (1 + t1_off / 100), 3), "label": t1_label},
        {"pct": 50, "price": round(current_ma20 * (1 + t2_off / 100), 3), "label": t2_label},
        {"pct": 20, "price": None, "label": "反弹确认"},
    ]


def main():
    proxy_path = os.path.join(ROOT, "data", "sector-proxy.json")
    with open(proxy_path) as f:
        cfg = json.load(f)

    meta = cfg.setdefault("etf_meta", {})

    for sym in ETF_SYMS:
        path = os.path.join(ROOT, "data", "etf", "daily", sym, "daily.jsonl")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            rows = [json.loads(l) for l in f if l.strip()]

        devs, current_ma20 = find_pullback_devs(rows)
        if not devs or current_ma20 is None:
            continue

        etf_name = None
        for name, code in cfg["variants"]["etf"].items():
            if code == sym:
                etf_name = name; break
        if not etf_name:
            continue

        p10 = sorted(devs)[max(0, int(len(devs) * 0.10))] if devs else 0
        p50 = sorted(devs)[max(0, int(len(devs) * 0.50))] if devs else 0
        p25 = sorted(devs)[max(0, int(len(devs) * 0.25))] if devs else 0

        tiers = compute_tiers(devs, current_ma20)
        print(f"{etf_name}({sym}): {len(devs)}次回调 MA20={current_ma20:.3f} "
              f"p10={p10:+.1f}% p25={p25:+.1f}% p50={p50:+.1f}%")
        for t in tiers:
            if t["price"]:
                print(f"  {t['pct']}% @ ¥{t['price']} ({t['label']})")
            else:
                print(f"  {t['pct']}% @ {t['label']}")

        entry = meta.setdefault(etf_name, {})
        entry["entry_tiers"] = tiers

    with open(proxy_path, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print("\n✅ sector-proxy.json 已更新")


if __name__ == "__main__":
    main()
