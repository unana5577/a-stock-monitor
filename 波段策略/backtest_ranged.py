"""
震荡市策略回测 v2 — 逐笔时间线 + 三组对比
===========================================
每只ETF总预算=10万(base+波段), 2只ETF共20万。
展示每个标的完整买卖时间线, 以及各组之间的差异。
"""
import json, os, sys, argparse
from datetime import date, timedelta
from typing import Dict, Any, List, Tuple
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, ROOT)

TARGET_SYMBOLS = ["sh515880", "sh512480"]
SYMBOL_NAMES = {"sh515880": "通信ETF", "sh512480": "半导体ETF"}

# ============================================================
# 顶层逻辑:
#   震荡市=定投建底仓 + 网格波段。两个维度构成三组:
#
#   维度1: 触发灵敏度 (sell_trigger / buy_trigger)
#     → 决定了"几步之内抓到波动"
#   维度2: 单笔仓位 (sell_ratio / buy_ratio)
#     → 决定了"每笔赚多少/亏多少"
#
#   三组不是简单调数字,而是代表三种交易性格:
#   - 默认(均衡): 中频中仓, 追求每笔确定利润
#   - 激进(捕手): 高频大仓, 不放过任何波动
#   - 保守(潜伏): 低频小仓, 只做大波段
# ============================================================

PER_ETF_TOTAL = 100_000   # 每只ETF总预算

PARAM_GROUPS = {
    "default": {
        "name":     "默认(均衡·中频中仓)",
        "logic":    "涨5%卖10%→每笔约赚5000; 跌3%买10%→每笔约花3000; 冷却1天防连击",
        "base_ratio":      0.6,     # 底仓6万/波段4万
        "batches":         3,       # 3批建底仓
        "sell_trigger_pct":5.0,     # 涨5%触发卖出
        "sell_ratio":      0.10,    # 卖出总仓位的10%
        "buy_trigger_pct": 3.0,     # 跌3%触发买入
        "buy_ratio":       0.10,    # 买入单只ETF总预算的10%
        "cooldown_days":   1,       # 同向冷却1天
    },
    "aggressive": {
        "name":     "激进(捕手·高频大仓)",
        "logic":    "涨3%卖15%→每笔约赚4500; 跌2%买12%→每笔约花3600; 无冷却",
        "base_ratio":      0.6,
        "batches":         3,
        "sell_trigger_pct":3.0,
        "sell_ratio":      0.15,
        "buy_trigger_pct": 2.0,
        "buy_ratio":       0.12,
        "cooldown_days":   0,
    },
    "conservative": {
        "name":     "保守(潜伏·低频小仓)",
        "logic":    "涨7%卖8%→每笔约赚5600但机会少; 跌4%买5%→每笔约花2000; 冷却2天",
        "base_ratio":      0.6,
        "batches":         3,
        "sell_trigger_pct":7.0,
        "sell_ratio":      0.08,
        "buy_trigger_pct": 4.0,
        "buy_ratio":       0.05,
        "cooldown_days":   2,
    },
}

# ============================================================
# 可调变量一览 (共 8 个):
# ============================================================
# 1. base_ratio       — 底仓占总预算比例 (0.4~0.8)
# 2. batches          — 建仓批次数 (2~5)
# 3. sell_trigger_pct — 涨幅触发卖出阈值% (3~8)
# 4. sell_ratio       — 卖出比例% (0.05~0.20)
# 5. buy_trigger_pct  — 跌幅触发买入阈值% (2~5)
# 6. buy_ratio        — 买入比例% (0.05~0.15)
# 7. cooldown_days    — 同向冷却天数 (0~3)
# 8. per_etf_total    — 每只ETF总预算 (外部,此处固定10万)
# ============================================================

def read_daily(path: str) -> List[dict]:
    if not os.path.exists(path): return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except: pass
    return rows

def filter_dates(rows: List[dict], start: str, end: str) -> List[dict]:
    return [r for r in rows if start <= r.get("date", "") <= end]

def fmt_pct(v): return f"{v:+.2f}%"
def fmt_cny(v): return f"{v:,.0f}"
def fmt_k(v):  return f"{v/1000:.1f}k"

def run_backtest(sym_data: dict, cfg: dict) -> dict:
    """单标的回测。返回完整时间线 + 统计"""
    base_ratio   = cfg["base_ratio"]
    batches      = cfg["batches"]
    sell_trig    = cfg["sell_trigger_pct"]
    sell_ratio   = cfg["sell_ratio"]
    buy_trig     = cfg["buy_trigger_pct"]
    buy_ratio    = cfg["buy_ratio"]
    cooldown     = cfg["cooldown_days"]

    results = {}
    for sym in TARGET_SYMBOLS:
        rows = sym_data[sym]
        if not rows: continue
        total = PER_ETF_TOTAL
        base_target = total * base_ratio
        batch_target = base_target / batches
        base_shares = 0; base_cost = 0.0; swing_lots = []
        phase = 0; status = "building"; cash = total
        trades = []; near_misses = []; equity_line = []
        last_signal = None; last_signal_idx = -999

        all_dates = [r["date"] for r in rows]

        for idx, row in enumerate(rows):
            px = row["close"]; day = row["date"]
            if not px or px <= 0: continue

            ts = base_shares + sum(l["shares"] for l in swing_lots)
            tv = ts * px
            eq = cash + tv

            pct_change = ((px - base_cost) / base_cost * 100) if base_cost > 0 and base_shares > 0 else 0
            pos_pct = tv / total if total > 0 else 0

            equity_line.append({"date": day, "equity": round(eq, 2)})

            # phase 0: building
            if status == "building":
                if phase < batches:
                    s = int(batch_target / px / 100) * 100
                    if s >= 100 and cash >= s * px:
                        cash -= s * px
                        ns = base_shares + s
                        base_cost = ((base_shares * base_cost + s * px) / ns) if ns > 0 else px
                        base_shares = ns; phase += 1
                        trades.append({"date": day, "type": "建仓", "action": "BUY",
                            "shares": s, "price": round(px,4),
                            "cost_basis": round(base_cost,4),
                            "note": f"第{phase}批/{batches} 均价{base_cost:.4f}"})
                        last_signal = "BUILD"; last_signal_idx = idx
                    else:
                        near_misses.append({"date": day, "type": "建仓(现金不足)",
                            "price": round(px,4), "note": f"需{s}股×{px}={s*px:.0f} 现金{cash:.0f}"})
                if phase >= batches:
                    status = "holding"
                    last_signal = None; last_signal_idx = -999
                    if not trades: continue
                    trades[-1]["note"] += " →底仓完成"

            # phase 1: holding
            elif status == "holding":
                cd_ok = (idx - last_signal_idx) > cooldown if cooldown > 0 else True

                # 卖出
                if pct_change >= sell_trig and ts > 0 and last_signal not in ("SELL", "BUILD") and cd_ok:
                    sv = tv * sell_ratio
                    ss = int(sv / px / 100) * 100
                    if ss >= 100:
                        rem = ss
                        if swing_lots:
                            nl = []
                            for lot in swing_lots:
                                ls = lot["shares"]
                                if rem > 0 and ls > 0:
                                    t = min(rem, ls); rem -= t
                                    if ls > t: nl.append({"shares": ls-t, "cost": lot["cost"], "entry_date": lot["entry_date"]})
                                else: nl.append(lot)
                            swing_lots = nl
                        if rem > 0 and base_shares > 0:
                            base_shares = max(0, base_shares - rem)
                        cash += ss * px
                        trades.append({"date": day, "type": "套利", "action": "SELL",
                            "shares": ss, "price": round(px,4),
                            "cost_basis": round(base_cost,4),
                            "note": f"浮盈{pct_change:+.1f}%≥{sell_trig}% 卖{ss}股@{px:.3f} 回笼{ss*px:.0f}"})
                        last_signal = "SELL"; last_signal_idx = idx
                elif pct_change >= sell_trig and ts > 0 and not cd_ok:
                    near_misses.append({"date": day, "type": f"套利(冷却中)",
                        "price": round(px,4), "note": f"浮盈{pct_change:+.1f}%达标 但距上次仅{idx-last_signal_idx}天 需≥{cooldown+1}天"})
                elif sell_trig <= pct_change < sell_trig + 1 and 0 < pct_change < sell_trig:
                    pass
                elif 0 < pct_change < sell_trig and pct_change >= sell_trig - 1.5:
                    near_misses.append({"date": day, "type": "套利(接近)",
                        "price": round(px,4), "note": f"浮盈{pct_change:+.1f}% 距触发差{sell_trig-pct_change:.1f}%"})

                # 买入
                if pct_change <= -buy_trig and ts > 0 and last_signal not in ("BUY", "BUILD") and cd_ok:
                    bv = total * buy_ratio
                    bs = int(bv / px / 100) * 100
                    if bs >= 100 and cash >= bs * px:
                        cash -= bs * px
                        swing_lots.append({"shares": bs, "cost": px, "entry_date": day})
                        trades.append({"date": day, "type": "吸筹", "action": "BUY",
                            "shares": bs, "price": round(px,4),
                            "cost_basis": round(base_cost,4),
                            "note": f"浮亏{pct_change:+.1f}%≤{-buy_trig}% 买{bs}股@{px:.3f} 花费{bs*px:.0f}"})
                        last_signal = "BUY"; last_signal_idx = idx
                elif pct_change <= -buy_trig and ts > 0 and not cd_ok:
                    near_misses.append({"date": day, "type": "吸筹(冷却中)",
                        "price": round(px,4), "note": f"浮亏{pct_change:+.1f}%达标 冷却中"})
                elif -buy_trig - 1.5 <= pct_change < -buy_trig:
                    near_misses.append({"date": day, "type": "吸筹(接近)",
                        "price": round(px,4), "note": f"浮亏{pct_change:+.1f}% 距触发差{abs(pct_change)-buy_trig:.1f}%"})

        # final snapshot
        final_px = rows[-1]["close"] if rows else 0
        ts = base_shares + sum(l["shares"] for l in swing_lots)
        final_eq = cash + ts * final_px
        total_pnl = final_eq - total
        peak_eq = total; max_dd = 0
        for pt in equity_line:
            if pt["equity"] > peak_eq: peak_eq = pt["equity"]
            dd = (peak_eq - pt["equity"]) / peak_eq * 100 if peak_eq > 0 else 0
            if dd > max_dd: max_dd = dd

        buy_total = sum(t["shares"]*t["price"] for t in trades if t["action"]=="BUY")
        sell_total= sum(t["shares"]*t["price"] for t in trades if t["action"]=="SELL")

        results[sym] = {
            "symbol": sym, "name": SYMBOL_NAMES.get(sym, sym),
            "final_price": round(final_px, 4),
            "base_shares": base_shares, "base_cost": round(base_cost, 4),
            "swing_shares": sum(l["shares"] for l in swing_lots),
            "swing_lots": len(swing_lots),
            "final_equity": round(final_eq, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl / total * 100, 2),
            "max_dd_pct": round(max_dd, 2),
            "cash": round(cash, 2),
            "buy_count": sum(1 for t in trades if t["type"] in ("建仓","吸筹")),
            "sell_count": sum(1 for t in trades if t["type"]=="套利"),
            "build_count": sum(1 for t in trades if t["type"]=="建仓"),
            "dip_count": sum(1 for t in trades if t["type"]=="吸筹"),
            "buy_value": round(buy_total, 2),
            "sell_value": round(sell_total, 2),
            "trades": trades,
            "near_misses": near_misses,
            "equity_line": equity_line[::max(1,len(equity_line)//30)],
            "first_day": rows[0]["date"], "last_day": rows[-1]["date"],
            "total_days": len(rows)
        }
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", default="compare",
        choices=["default","aggressive","conservative","compare"])
    parser.add_argument("--start", default="2025-10-01")
    parser.add_argument("--end",   default="2026-04-30")
    args = parser.parse_args()

    sym_data = {}
    for sym in TARGET_SYMBOLS:
        path = os.path.join(ROOT, "data", "etf", "daily", sym, "daily.jsonl")
        sym_data[sym] = filter_dates(read_daily(path), args.start, args.end)

    groups = ["default","aggressive","conservative"] if args.group=="compare" else [args.group]

    all_results = {}
    for gk in groups:
        cfg = PARAM_GROUPS[gk]
        all_results[gk] = run_backtest(sym_data, cfg)

    # ---------- print ----------
    for gk in groups:
        cfg = PARAM_GROUPS[gk]
        res = all_results[gk]
        combined_pnl = sum(res[s]["total_pnl"] for s in TARGET_SYMBOLS)
        combined_eq  = sum(res[s]["final_equity"] for s in TARGET_SYMBOLS)
        total_buys   = sum(res[s]["buy_count"] for s in TARGET_SYMBOLS)
        total_sells  = sum(res[s]["sell_count"] for s in TARGET_SYMBOLS)
        total_trades = sum(len(res[s]["trades"]) for s in TARGET_SYMBOLS)

        print(f"\n{'='*70}")
        print(f"  {cfg['name']}")
        print(f"  {cfg['logic']}")
        print(f"{'='*70}")
        print(f"  区间: {res[TARGET_SYMBOLS[0]]['first_day']} ~ {res[TARGET_SYMBOLS[0]]['last_day']}")
        print(f"  总预算: ¥{fmt_cny(PER_ETF_TOTAL*2)} (每只10万)  |  底仓比: {cfg['base_ratio']*100:.0f}%")
        print(f"  总盈亏: ¥{fmt_cny(combined_pnl)} ({combined_pnl/(PER_ETF_TOTAL*2)*100:+.2f}%)")
        print(f"  总交易: {total_trades}笔 ({total_buys}买/{total_sells}卖)")
        print()

        for sym in TARGET_SYMBOLS:
            r = res[sym]
            print(f"  ┌─ {r['name']} ─────────────────────────────────")
            print(f"  │ 盈亏: ¥{fmt_cny(r['total_pnl'])} ({r['total_pnl_pct']:+.2f}%) | 最大回撤: {r['max_dd_pct']:.2f}%")
            print(f"  │ 交易: {len(r['trades'])}笔 "
                  f"(建仓{r['build_count']}/吸筹{r['dip_count']}/套利{r['sell_count']})")
            print(f"  │ 终态: 底仓{r['base_shares']}股@{r['base_cost']:.4f} "
                  f"+ 波段{r['swing_shares']}股({r['swing_lots']}批)")
            print(f"  │ 买入额: ¥{fmt_cny(r['buy_value'])} | 卖出额: ¥{fmt_cny(r['sell_value'])}")
            print(f"  │ 剩余现金: ¥{fmt_cny(r['cash'])}")
            print(f"  │")
            if r["trades"]:
                print(f"  │ 完整时间线:")
                for t in r["trades"]:
                    amt = t["shares"] * t["price"]
                    tag = "🟢" if t["type"]=="建仓" else ("🔴" if t["type"]=="套利" else "🔵")
                    print(f"  │  {tag} [{t['date']}] {t['type']} {t['shares']}股@{t['price']:.4f} "
                          f"¥{fmt_cny(amt)} | {t['note']}")
            nm = r.get("near_misses", [])
            if nm:
                print(f"  │")
                print(f"  │ 接近触发(未执行,共{len(nm)}次):")
                for n in nm[-8:]:
                    print(f"  │    [{n['date']}] {n['type']} | {n['note']}")
            print()

    # ---------- 三组对比 ----------
    if len(groups) > 1:
        print(f"{'='*70}")
        print(f"  三组对比总览 (每只10万, 2只共20万)")
        print(f"{'='*70}")
        hdr = f"  {'参数组':<20} {'总盈亏':>8} {'总交易':>7} {'买/卖':>7} {'通信盈亏':>8} {'半导体盈亏':>8}"
        print(hdr)
        print("  " + "-"*65)
        for gk in groups:
            res = all_results[gk]
            pnl = sum(res[s]["total_pnl"] for s in TARGET_SYMBOLS)
            ntr = sum(len(res[s]["trades"]) for s in TARGET_SYMBOLS)
            nb  = sum(res[s]["buy_count"] for s in TARGET_SYMBOLS)
            ns  = sum(res[s]["sell_count"] for s in TARGET_SYMBOLS)
            pnl_a = res["sh515880"]["total_pnl"]
            pnl_b = res["sh512480"]["total_pnl"]
            print(f"  {PARAM_GROUPS[gk]['name']:<20} {pnl/(PER_ETF_TOTAL*2)*100:>+6.2f}% "
                  f"{ntr:>6}笔 {nb}/{ns:>3} "
                  f"{pnl_a/PER_ETF_TOTAL*100:>+6.2f}% {pnl_b/PER_ETF_TOTAL*100:>+6.2f}%")

        # 差异分析
        res_d = all_results["default"]
        res_a = all_results["aggressive"]
        res_c = all_results["conservative"]
        print(f"\n  差异分析:")
        print(f"  默认 vs 激进: 激进触发更敏感(3%/2% vs 5%/3%) 仓位更重(15%/12% vs 10%/10%)")
        nd = sum(len(res_d[s]["trades"]) for s in TARGET_SYMBOLS)
        na = sum(len(res_a[s]["trades"]) for s in TARGET_SYMBOLS)
        nc = sum(len(res_c[s]["trades"]) for s in TARGET_SYMBOLS)
        print(f"    交易数: 默认{nd} / 激进{na} / 保守{nc}")
        for sym in TARGET_SYMBOLS:
            bd = res_d[sym]["dip_count"]; ba = res_a[sym]["dip_count"]; bc = res_c[sym]["dip_count"]
            sd = res_d[sym]["sell_count"]; sa = res_a[sym]["sell_count"]; sc = res_c[sym]["sell_count"]
            print(f"    {SYMBOL_NAMES[sym]}: 吸筹 默认{bd}/激进{ba}/保守{bc}  套利 默认{sd}/激进{sa}/保守{sc}")

        # tunable variables
        print(f"\n  可调参数: 共8个")
        print(f"    每只预算: {fmt_cny(PER_ETF_TOTAL)} (外部)")
        print(f"    策略内7个: base_ratio / batches / sell_trigger / sell_ratio / buy_trigger / buy_ratio / cooldown")
        print(f"    各参数含义与建议范围见文档: 波段策略/震荡市策略_变量手册.md")

    out_path = os.path.join(DIR, "data", f"backtest_ranged_{args.group}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({gk: {sym: {k:v for k,v in r.items() if k not in ("equity_line",)} 
                        for sym, r in res.items()} 
                   for gk, res in all_results.items()}, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果: {out_path}")

if __name__ == "__main__":
    main()
