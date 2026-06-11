"""
四阶段策略回测
==============
阶段判断 + 子策略调度 + 降级处理。
通信ETF(sh515880) + 半导体ETF(sh512480), 各10万预算, 2025-10 ~ 2026-04。
"""
import json, os, sys, argparse
from typing import Dict, List

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, DIR)

from stage_detector import detect_stage, STAGE_RANGED, STAGE_STARTUP, STAGE_UPTREND, STAGE_DECLINING, STAGE_DEFENSE
from stage_strategies import PositionState, execute_day
from adaptive_params import init_shadow, calibrate, shadow_pnl, strategy_pnl, DEFAULT_PARAMS

TARGET_SYMBOLS = ["sh515880", "sh512480", "sh563530", "sh516510", "sh562500"]
SYMBOL_NAMES = {"sh515880": "通信ETF", "sh512480": "半导体ETF", "sh563530": "商业航天ETF", "sh516510": "云计算ETF", "sh562500": "机器人ETF"}
PER_ETF = 100_000
STAGE_ICONS = {STAGE_RANGED: "🔵", STAGE_STARTUP: "🟡", STAGE_UPTREND: "🟢", STAGE_DECLINING: "🟠", STAGE_DEFENSE: "🔴"}
STAGE_LABELS = {STAGE_RANGED: "震荡", STAGE_STARTUP: "启动", STAGE_UPTREND: "主升", STAGE_DECLINING: "下跌", STAGE_DEFENSE: "防守"}

def read_daily(path: str) -> List[dict]:
    rows = []
    if not os.path.exists(path): return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: rows.append(json.loads(line))
            except: pass
    return rows

def filter_dates(rows: List[dict], start: str, end: str) -> List[dict]:
    return [r for r in rows if start <= r.get("date","") <= end]

def fmt_cny(v): return f"{v:,.0f}"
def fmt_pct(v): return f"{v:+.2f}%"

def handle_downgrade(pos: PositionState, old_stage: str, new_stage: str, px: float, day: str) -> List[dict]:
    """处理阶段切换时的仓位调整"""
    trades = []
    ts = pos.total_shares

    # 进入防守: 100%清仓
    if new_stage == STAGE_DEFENSE and ts > 0:
        pos.cash += ts * px
        trades.append({"date": day, "type": "死叉清仓", "action": "SELL", "shares": ts,
            "price": round(px,4), "note": f"{STAGE_LABELS.get(old_stage,old_stage)}→防守, 清仓{ts}股 @{px:.4f}"})
        pos.sell_cooldown = 1
        pos.base_shares = 0; pos.base_cost = 0.0; pos.swing_lots = []
        pos.build_phase = 0; pos.entry_peak = 0.0
        pos.params = dict(DEFAULT_PARAMS)
        pos.shadow_shares = 0; pos.shadow_cost = 0.0
        return trades

    # 主升/启动 → 下跌: 减至50% (牛末止损)
    if new_stage == STAGE_DECLINING and old_stage in (STAGE_UPTREND, STAGE_STARTUP) and ts > 0:
        target_val = pos.total * 0.50
        current_val = ts * px
        if current_val > target_val:
            sell_shares = int((current_val - target_val) / px / 100) * 100
            if sell_shares >= 100:
                _sell(pos, sell_shares, px)
                trades.append({"date": day, "type": "牛末止损", "action": "SELL", "shares": sell_shares,
                    "price": round(px,4),
                    "note": f"{STAGE_LABELS.get(old_stage,old_stage)}→下跌, 减至50% 卖出{sell_shares}股 @{px:.4f}"})
                pos.sell_cooldown = 1

    # 主升/启动 → 震荡: 减至70%
    if new_stage == STAGE_RANGED and old_stage in (STAGE_UPTREND, STAGE_STARTUP) and ts > 0:
        target_val = pos.total * 0.70
        current_val = ts * px
        if current_val > target_val * 1.05:
            excess_val = current_val - target_val
            sell_shares = int(excess_val / px / 100) * 100
            if sell_shares >= 100:
                _sell(pos, sell_shares, px)
                trades.append({"date": day, "type": "降级减仓", "action": "SELL", "shares": sell_shares,
                    "price": round(px,4),
                    "note": f"{STAGE_LABELS.get(old_stage,old_stage)}→震荡, 减至70% 卖出{sell_shares}股"})
                pos.sell_cooldown = 1

    pos.stage = new_stage
    return trades

def _sell(pos, shares, px):
    rem = shares
    if pos.swing_lots:
        nl = []
        for lot in pos.swing_lots:
            ls = lot["shares"]
            if rem > 0 and ls > 0:
                t = min(rem, ls); rem -= t
                if ls > t: nl.append({"shares": ls-t, "cost": lot["cost"], "entry_date": lot.get("entry_date","")})
            else: nl.append(lot)
        pos.swing_lots = nl
    if rem > 0 and pos.base_shares > 0:
        pos.base_shares = max(0, pos.base_shares - rem)
    pos.cash += shares * px

def run_backtest(start: str, end: str) -> dict:
    sym_data = {}
    for sym in TARGET_SYMBOLS:
        path = os.path.join(ROOT, "data", "etf", "daily", sym, "daily.jsonl")
        sym_data[sym] = filter_dates(read_daily(path), start, end)

    all_days = sorted(set(
        r["date"] for sym in TARGET_SYMBOLS for r in sym_data[sym]
    ))
    all_days = [d for d in all_days if all(
        any(r["date"]==d for r in sym_data[sym]) for sym in TARGET_SYMBOLS
    )]

    results = {}
    for sym in TARGET_SYMBOLS:
        pos = PositionState(sym, PER_ETF)
        rows = sym_data[sym]
        trades = []
        equity_line = []
        stage_log = []
        calibrations = []

        stage_persistence = {}  # {stage: consecutive_days}
        current_stage = None

        for day in all_days:
            row = next((r for r in rows if r["date"] == day), None)
            if not row: continue
            px = row["close"]
            if not px or px <= 0: continue

            idx = rows.index(row)
            detected_stage, diag = detect_stage(rows, idx)

            # stage persistence: only confirm after N consecutive days
            PERSIST_DAYS = 3
            for s in stage_persistence:
                if s == detected_stage:
                    stage_persistence[s] += 1
                else:
                    stage_persistence[s] = 0
            if detected_stage not in stage_persistence:
                stage_persistence[detected_stage] = 1

            if current_stage is None:
                current_stage = detected_stage
                stage = detected_stage
            elif current_stage != detected_stage and stage_persistence.get(detected_stage, 0) >= PERSIST_DAYS:
                stage = detected_stage
                stage_persistence = {detected_stage: PERSIST_DAYS}
            elif current_stage == detected_stage:
                stage = detected_stage
            else:
                stage = current_stage

            if stage != current_stage:
                current_stage = stage

            old_stage = pos.stage
            if stage != old_stage:
                downgrade_trades = handle_downgrade(pos, old_stage, stage, px, day)
                trades.extend(downgrade_trades)

            day_trades = execute_day(pos, stage, px, day, diag)
            trades.extend(day_trades)

            # shadow + calibrate
            if pos.shadow_shares <= 0:
                init_shadow(pos, px)
            cal_result = calibrate(pos, px, stage)
            if cal_result:
                calibrations.append({"date": day, "note": cal_result,
                    "params": dict(pos.params)})

            eq = pos.equity(px)
            equity_line.append({"date": day, "equity": round(eq, 2), "stage": stage})

            if stage != old_stage:
                stage_log.append({
                    "date": day, "from": STAGE_LABELS.get(old_stage, old_stage),
                    "to": STAGE_LABELS.get(stage, stage),
                    "price": round(px,4),
                    "ma20": diag.get("ma20"), "ma60": diag.get("ma60"),
                    "slope": diag.get("ma20_slope")
                })

        final_px = rows[-1]["close"]
        final_eq = pos.equity(final_px)
        pnl = final_eq - PER_ETF
        peak = PER_ETF; max_dd = 0.0
        for pt in equity_line:
            if pt["equity"] > peak: peak = pt["equity"]
            dd = (peak - pt["equity"]) / peak * 100 if peak > 0 else 0
            if dd > max_dd: max_dd = dd

        buy_n = sum(1 for t in trades if t["action"]=="BUY")
        sell_n= sum(1 for t in trades if t["action"]=="SELL")
        results[sym] = {
            "symbol": sym, "name": SYMBOL_NAMES.get(sym,sym),
            "final_price": round(final_px,4),
            "final_equity": round(final_eq,2),
            "total_pnl": round(pnl,2),
            "total_pnl_pct": round(pnl/PER_ETF*100,2),
            "max_dd_pct": round(max_dd,2),
            "base_shares": pos.base_shares,
            "base_cost": round(pos.base_cost,4),
            "swing_shares": sum(l["shares"] for l in pos.swing_lots),
            "cash": round(pos.cash,2),
            "trades": trades,
            "stage_log": stage_log,
            "equity_line": equity_line[::max(1,len(equity_line)//25)],
            "buy_count": buy_n, "sell_count": sell_n,
            "calibrations": calibrations,
            "buyers": sum(1 for t in trades if t["type"] in ("建仓","吸筹","试探","加仓","趋势加仓")),
            "sellers": sum(1 for t in trades if t["type"] in ("套利","防守清仓","降级清仓","降级减仓")),
        }
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-10-01")
    parser.add_argument("--end", default="2026-04-30")
    args = parser.parse_args()

    res = run_backtest(args.start, args.end)

    total_pnl = sum(res[s]["total_pnl"] for s in TARGET_SYMBOLS)
    total_eq  = sum(res[s]["final_equity"] for s in TARGET_SYMBOLS)
    total_trades = sum(len(res[s]["trades"]) for s in TARGET_SYMBOLS)

    print(f"\n{'='*70}")
    print(f"  四阶段策略调度回测")
    print(f"  区间: {args.start} ~ {args.end} | 每只预算: ¥{fmt_cny(PER_ETF)} | 共 ¥{fmt_cny(PER_ETF*2)}")
    print(f"  总盈亏: ¥{fmt_cny(total_pnl)} ({total_pnl/(PER_ETF*2)*100:+.2f}%)")
    print(f"  总交易: {total_trades}笔")
    print()

    for sym in TARGET_SYMBOLS:
        r = res[sym]
        print(f"  ╔══ {r['name']} ═══════════════════════════════════")
        print(f"  ║ 盈亏: ¥{fmt_cny(r['total_pnl'])} ({fmt_pct(r['total_pnl_pct'])})"
              f" | 最大回撤: {r['max_dd_pct']:.2f}%")
        print(f"  ║ 交易: {len(r['trades'])}笔 ({r['buyers']}买/{r['sellers']}卖)"
              f" | 终态: 底仓{r['base_shares']}股 + 波段{r['swing_shares']}股"
              f" | 现金: ¥{fmt_cny(r['cash'])}")
        print(f"  ║")
        print(f"  ║ 阶段切换日志:")
        if r["stage_log"]:
            for sl in r["stage_log"]:
                icon = STAGE_ICONS.get(STAGE_LABELS.get(sl["to"]) or sl["to"], "")
                print(f"  ║   [{sl['date']}] {sl['from']} → {icon}{sl['to']} "
                      f"@{sl['price']} MA20={sl.get('ma20','?')} MA60={sl.get('ma60','?')}")
        print(f"  ║")
        print(f"  ║ 交易明细:")
        for t in r["trades"]:
            icon = "🟢" if t["action"]=="BUY" else ("🔴" if t["action"]=="SELL" else "⚪")
            amt = t["shares"] * t["price"]
            print(f"  ║   {icon} [{t['date']}] {t['type']} {t['shares']}股"
                  f"@{t['price']:.4f} ¥{fmt_cny(amt)} | {t['note']}")
        print(f"  ║")
        eqc = r["equity_line"]
        if eqc:
            print(f"  ║ 净值曲线:")
            for pt in [eqc[0], eqc[len(eqc)//2], eqc[-1]]:
                icon = STAGE_ICONS.get(pt.get("stage", ""), "")
                print(f"  ║   {pt['date']} {icon} ¥{fmt_cny(pt['equity'])}")
        cals = r.get("calibrations", [])
        if cals:
            print(f"  ║")
            print(f"  ║ 参数校准日志 ({len(cals)}次):")
            for c in cals:
                print(f"  ║   [{c['date']}] {c['note']}")
        print()

    print(f"  ┌─────────────────────────────────────────────┐")
    print(f"  │ 对比: 四阶段调度 vs 买入持有 vs 震荡策略(前次) │")
    print(f"  ├────────────┬──────────┬──────────┬──────────┤")
    print(f"  │ {'标的':<8} {'四阶段':>8} {'买入持有':>8} {'震荡(v2)':>8} │")

    hold = {}
    for sym in TARGET_SYMBOLS:
        rows = sym_data = filter_dates(
            read_daily(os.path.join(ROOT, "data", "etf", "daily", sym, "daily.jsonl")),
            args.start, args.end
        )
        if rows:
            buy_px = rows[0]["close"]
            sell_px = rows[-1]["close"]
            shares = int(PER_ETF / buy_px / 100) * 100
            hold[sym] = round((shares * sell_px - PER_ETF) / PER_ETF * 100, 2)

    for sym in TARGET_SYMBOLS:
        staged = res[sym]
        h = hold.get(sym, 0)
        print(f"  │ {SYMBOL_NAMES.get(sym,sym):<8} {staged['total_pnl_pct']:>+7.2f}% {h:>+7.2f}% {'+23%':>8}")

    combined = total_pnl / (PER_ETF * 2) * 100
    hold_combined = (hold.get("sh515880",0) + hold.get("sh512480",0)) / 2
    print(f"  │ {'合计':<8} {combined:>+7.2f}% {hold_combined:>+7.2f}% {'+23%':>8}")
    print(f"  └────────────┴──────────┴──────────┴──────────┘")

    out_path = os.path.join(DIR, "data", "backtest_staged.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({sym: {k:v for k,v in r.items() if k not in ("equity_line",)}
                   for sym, r in res.items()}, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  结果: {out_path}")

if __name__ == "__main__":
    main()
