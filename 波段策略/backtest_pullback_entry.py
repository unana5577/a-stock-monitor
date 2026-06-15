"""
回调买入价回测: 主升→回调→分批建仓 vs 收益
===================================================
2025-05-01 起, 每只ETF:
  1. 找主升→回调样本(MA20>MA60, 最低点未破MA60)
  2. 模拟4种建仓策略:
     A: 50%@MA20 + 30%@MA20-5% + 20%@反弹
     B: 30%@MA20 + 50%@MA20-5% + 20%@反弹
     C: 20%@MA20 + 50%@MA20-5% + 30%@反弹
     D: 100%@MA20 (一把买入, 对照)
  3. 统计T+5/T+10/T+20收益分布
"""
import json, os, sys
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, DIR)
from stage_detector import detect_stage, calc_ma, STAGE_UPTREND, STAGE_DEFENSE

FROM_DATE = "2025-05-01"
ETF_SYMS = ["sh512480","sh512400","sh515880","sh516010","sh516510","sh562500","sh563530","sh515120","sh516160","sh562590"]

STRATEGIES = {
    "A: 50/30/20": [("ma20", 0.50), ("ma20-5%", 0.30), ("rebound", 0.20)],
    "B: 30/50/20": [("ma20", 0.30), ("ma20-5%", 0.50), ("rebound", 0.20)],
    "C: 20/50/30": [("ma20", 0.20), ("ma20-5%", 0.50), ("rebound", 0.30)],
    "D: 一把梭":   [("ma20", 1.0)],
}


def find_pullback_samples(rows):
    """找每个主升段中的独立回调事件"""
    closes = [r["close"] for r in rows]
    opens = [r.get("open", closes[i]) for i, r in enumerate(rows)]
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)

    samples = []
    i = 0
    while i < len(rows):
        if rows[i]["date"] < FROM_DATE:
            i += 1
            continue
        stage, _ = detect_stage(rows, i)
        if stage != STAGE_UPTREND:
            i += 1
            continue

        # 找到此段主升的结束点(变为非主升且非立即回主升)
        ut_start = i
        i += 1
        while i < len(rows):
            s, _ = detect_stage(rows, i)
            if s == STAGE_UPTREND:
                i += 1
                continue
            if s == STAGE_DEFENSE:
                break
            # 非主升、非防守: 回调开始
            pb_start = i
            low_idx = i
            low_price = closes[i]
            i += 1
            while i < len(rows):
                s, _ = detect_stage(rows, i)
                if s == STAGE_UPTREND or s == STAGE_DEFENSE:
                    break
                if closes[i] < low_price:
                    low_idx = i
                    low_price = closes[i]
                i += 1

            m60_val = ma60[low_idx]
            if m60_val and low_price > m60_val:
                pb_end = i - 1
                rebound_idx = None
                for r_i in range(low_idx + 1, min(i + 5, len(rows))):
                    m20_ri = ma20[r_i]
                    if m20_ri and closes[r_i] > m20_ri and opens[r_i] < closes[r_i]:
                        rebound_idx = r_i
                        break

                samples.append({
                    "rows": rows,
                    "ut_start": ut_start,
                    "pb_start": pb_start,
                    "pb_end": pb_end,
                    "low_idx": low_idx,
                    "low_price": low_price,
                    "rebound_idx": rebound_idx,
                    "ma20": ma20[low_idx],
                    "ma60": m60_val,
                    "uptrend_date": rows[ut_start]["date"],
                    "pullback_date": rows[low_idx]["date"],
                })

            if s == STAGE_DEFENSE:
                i += 1
                break
            # else: STAGE_UPTREND, 继续外层while找下一个回调
        i += 1

    return samples


def simulate_pullback_buy(rows, sample):
    """对一个回调样本模拟各策略建仓和收益"""
    closes = [r["close"] for r in rows]
    ma20 = sample["ma20"]
    low_price = sample["low_price"]
    low_idx = sample["low_idx"]
    rebound_idx = sample.get("rebound_idx")

    if ma20 is None or ma20 <= 0:
        return None

    ma20_5pct = ma20 * 0.95
    results = {}

    for name, tranches in STRATEGIES.items():
        cost = 0.0
        filled = 0.0

        for trigger, alloc in tranches:
            if trigger == "ma20":
                price = ma20
            elif trigger == "ma20-5%":
                price = ma20_5pct
            elif trigger == "rebound":
                if rebound_idx:
                    price = closes[rebound_idx]
                else:
                    continue

            if low_price > price:
                continue

            filled += alloc
            cost += alloc * price

        if filled <= 0 or cost <= 0:
            continue

        avg_cost = cost / filled
        exit_idx = rebound_idx if rebound_idx else low_idx

        def pnl_at(offset_days):
            ei = min(exit_idx + offset_days, len(rows) - 1)
            exit_price = closes[ei]
            ret = (exit_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
            return rows[ei]["date"], round(ret, 2)

        results[name] = {
            "symbol": sample.get("symbol", "?"),
            "low_date": rows[low_idx]["date"],
            "low_price": round(low_price, 4),
            "ma20": round(ma20, 4),
            "avg_cost": round(avg_cost, 4),
            "filled": round(filled, 2),
            "rebound": rebound_idx is not None,
            "pnl_5d": pnl_at(5),
            "pnl_10d": pnl_at(10),
            "pnl_20d": pnl_at(20),
        }

    return results


def main():
    all_pullbacks = []
    for sym in ETF_SYMS:
        path = os.path.join(ROOT, "data", "etf", "daily", sym, "daily.jsonl")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            rows = [json.loads(l) for l in f if l.strip()]
        samples = find_pullback_samples(rows)
        all_pullbacks.extend(samples)
        print(f"{sym}: {len(samples)} pullbacks")

    print(f"\n总计: {len(all_pullbacks)} 个回调样本\n")

    strategy_returns = defaultdict(lambda: defaultdict(list))
    # 仅双档触发的样本(低点≤MA20-5%), 纯仓位比例对比
    deep_returns = defaultdict(lambda: defaultdict(list))

    for s in all_pullbacks:
        rows_data = s.pop("rows")
        sim = simulate_pullback_buy(rows_data, s)
        if not sim:
            continue
        deep_triggered = s["low_price"] <= s["ma20"] * 0.95
        for name, r in sim.items():
            for horizon in ["pnl_5d", "pnl_10d", "pnl_20d"]:
                strategy_returns[name][horizon].append(r[horizon][1])
                if deep_triggered:
                    deep_returns[name][horizon].append(r[horizon][1])

    print("=== 分批建仓策略对比(全部样本) ===")
    for name in ["A: 50/30/20", "B: 30/50/20", "C: 20/50/30", "D: 一把梭"]:
        rets = strategy_returns.get(name, {})
        print(f"\n{name}:")
        for horizon in ["pnl_5d", "pnl_10d", "pnl_20d"]:
            vals = rets.get(horizon, [])
            if not vals: continue
            n = len(vals); mean = sum(vals)/n
            win = sum(1 for v in vals if v>0)
            pos = [v for v in vals if v>0]; neg = [v for v in vals if v<0]
            avg_win = sum(pos)/len(pos) if pos else 0
            avg_loss = sum(neg)/len(neg) if neg else 0
            print(f"  T{horizon[4:]}  n={n}  mean={mean:+.1f}%  胜率={win/n*100:.0f}%  "
                  f"均盈={avg_win:+.1f}% 均亏={avg_loss:.1f}%")

    deep_count = len(deep_returns.get("B: 30/50/20", {}).get("pnl_5d", []))
    print(f"\n=== 双档触发(低点≤MA20-5%, 纯仓位比例对比, n={deep_count}) ===")
    for name in ["A: 50/30/20", "B: 30/50/20", "C: 20/50/30", "D: 一把梭"]:
        rets = deep_returns.get(name, {})
        vals_5 = rets.get("pnl_5d", [])
        vals_10 = rets.get("pnl_10d", [])
        vals_20 = rets.get("pnl_20d", [])
        if vals_10:
            m = sum(vals_10)/len(vals_10)
            win = sum(1 for v in vals_10 if v>0)/len(vals_10)*100
            marker = " ← 推荐" if name.startswith("B") else ""
            print(f"  {name}: T+5={sum(vals_5)/len(vals_5):+.1f}%  T+10={m:+.1f}%({win:.0f}%胜)  T+20={sum(vals_20)/len(vals_20):+.1f}%{marker}")

    print("\n=== 建议 ===")
    d_deep = deep_returns.get("D: 一把梭", {}).get("pnl_10d", [])
    b_deep = deep_returns.get("B: 30/50/20", {}).get("pnl_10d", [])
    if b_deep and d_deep:
        print(f"B(30/50/20) T+10={sum(b_deep)/len(b_deep):+.1f}% vs 一把梭={sum(d_deep)/len(d_deep):+.1f}%")
    total = len(all_pullbacks)
    missed = total - len(strategy_returns.get("D: 一把梭", {}).get("pnl_5d", []))
    print(f"一把梭错过 {missed}/{total} 次回调(价格未触MA20, 但触MA20-5%)")
    print("结论: 金字塔加仓 30%@MA20 + 50%@MA20-5% + 20%@反弹")


if __name__ == "__main__":
    main()
