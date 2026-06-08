"""
policy_runner.py — 波段策略批量计算 + 状态持久化
=================================================
命令行入口, 每日盘后运行:

  python3 波段策略/policy_runner.py [--date 2026-06-08] [--replay] [--symbols sh512480,sh512400]

流程:
  1. 读取 lifecycle.json 获取当日信号
  2. 读取 daily.jsonl + market_amount 计算 MA20 特征
  3. 读取昨日 state 文件
  4. 逐 ETF 跑 compute_policy()
  5. 保存 state 文件
  6. 输出 policy_{date}.json 供 API 消费
"""
import json
import os
import sys
import argparse
from datetime import date, timedelta
from typing import Optional

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, ROOT)

from 波段策略.m1_policy import (
    compute_policy, load_state, save_state, load_params,
    get_bias, get_bias_max, get_close, get_signal_strength,
    is_momentum_healthy
)

ETF_SYMBOLS = [
    "sh512400", "sh512480", "sh515120", "sh515880",
    "sh516010", "sh516160", "sh516510", "sh562500", "sh563530"
]

SYMBOL_NAME_MAP = {
    "sh512400": "有色金属ETF",
    "sh512480": "半导体ETF",
    "sh515120": "创新药ETF",
    "sh515880": "通信ETF",
    "sh516010": "游戏ETF",
    "sh516160": "新能源ETF",
    "sh516510": "云计算ETF",
    "sh562500": "机器人ETF",
    "sh563530": "商业航天ETF",
}


def read_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def read_market_amount(path: str) -> dict:
    """读取市场成交额, 返回 {date: amount}"""
    rows = read_jsonl(path)
    return {r["date"]: r.get("amount", r.get("etf_amount", 0)) for r in rows if r.get("date")}


def compute_amount_share_series(etf_daily: list, market_amount: dict) -> list:
    """计算 amount_share 序列: etf_amount / market_amount"""
    series = []
    for r in etf_daily:
        d = r.get("date", "")
        etf_amt = r.get("amount", 0)
        mkt_amt = market_amount.get(d, 0)
        if mkt_amt > 0:
            series.append({"date": d, "value": etf_amt / mkt_amt})
    return series


def calc_ma20_features(amount_share_series: list) -> dict:
    """从 amount_share 序列计算 MA20 特征"""
    if not amount_share_series:
        return {"Amount_Share_MA20": 0, "Amount_Share_Change20": 0, "Amount_Share_DaysUp": 0}

    values = [s["value"] for s in amount_share_series]
    n = len(values)

    ma20 = sum(values[-20:]) / min(n, 20) if n > 0 else 0
    latest = values[-1] if n > 0 else 0
    change20 = latest / ma20 - 1 if ma20 > 0 else 0

    # 连续抬升天数
    days_up = 0
    for i in range(n - 1, 0, -1):
        window20_i = sum(values[max(0, i-19):i+1]) / min(i+1, 20) if i >= 0 else 0
        window20_prev = sum(values[max(0, i-20):i]) / min(i, 20) if i > 0 else 0
        if window20_i > window20_prev:
            days_up += 1
        else:
            break

    return {
        "Amount_Share_MA20": round(ma20, 6),
        "Amount_Share_Change20": round(change20, 4),
        "Amount_Share_DaysUp": days_up
    }


def load_lifecycle_signals(lifecycle_path: str) -> dict:
    """读取 lifecycle.json, 返回 {symbol: {动能,资金行为,...}}"""
    if not os.path.exists(lifecycle_path):
        return {}
    with open(lifecycle_path) as f:
        lc = json.load(f)
    items = lc.get("data", lc.get("items", []))
    result = {}
    for item in items:
        sym = item.get("symbol", "")
        if not sym:
            continue
        result[sym] = item
    return result


def load_warmup(warmup_path: str) -> dict:
    """读取 warmup-60.json, 返回 {symbol: [daily rows]}"""
    if not os.path.exists(warmup_path):
        return {}
    with open(warmup_path) as f:
        w = json.load(f)
    return w.get("history", {})


def run_policy_for_day(
    target_date: str,
    symbols: list = None,
    lifecycle_path: str = None,
    warmup_path: str = None,
    market_amount_path: str = None
) -> dict:
    if symbols is None:
        symbols = ETF_SYMBOLS
    if lifecycle_path is None:
        lifecycle_path = os.path.join(ROOT, "data", "lifecycle", "lifecycle.json")
    if warmup_path is None:
        warmup_path = os.path.join(ROOT, "data", "warmup", "warmup-60.json")
    if market_amount_path is None:
        market_amount_path = os.path.join(ROOT, "data", "market", "daily", "amount", "daily.jsonl")

    lifecycle_signals = load_lifecycle_signals(lifecycle_path)
    warmup = load_warmup(warmup_path)
    market_amount = read_market_amount(market_amount_path)

    results = {}

    for sym in symbols:
        signal = lifecycle_signals.get(sym, {})
        ind = signal.get("指标数据", {})

        # 读取该 ETF 的日线原始数据
        etf_daily_path = os.path.join(ROOT, "data", "etf", "daily", sym, "daily.jsonl")
        etf_daily_raw = read_jsonl(etf_daily_path)

        # 计算 MA20 特征
        amt_series = compute_amount_share_series(etf_daily_raw, market_amount)
        ma20_features = calc_ma20_features(amt_series)

        # 合并特征到指标数据
        enriched_ind = {**ind, **ma20_features}
        enriched_signal = {**signal, "指标数据": enriched_ind}

        # 读取昨日状态
        pct_p80 = ind.get("Pct_P80", ind.get("pct_p80", 1.5))
        yesterday_state = load_state(sym, pct_p80)

        # 跑状态机
        result = compute_policy(
            signals_today=enriched_signal,
            state_yesterday=yesterday_state,
            etf_symbol=sym,
            date=target_date,
            daily_raw=etf_daily_raw
        )

        # 保存状态
        save_state({
            "symbol": sym,
            "trend_state": result["trend_state"],
            "exit_reason": yesterday_state.get("exit_reason"),
            "exit_date": yesterday_state.get("exit_date"),
            "entry_date": yesterday_state.get("entry_date"),
            "position_level": result["position_level"],
            "target_weight": result.get("target_weight", 0),
            "peak_equity": yesterday_state.get("peak_equity", 0),
            "pct_p80": pct_p80,
            "stop_warn_line": result["stop_warn_line"],
            "stop_exec_line": result["stop_exec_line"],
            "building_entry_low": yesterday_state.get("building_entry_low"),
            "as_of": target_date,
            "history": yesterday_state.get("history", [])
        })

        results[sym] = result

    # 输出汇总 JSON
    output = {
        "day": target_date,
        "policies": results
    }

    policy_dir = os.path.join(DIR, "data")
    os.makedirs(policy_dir, exist_ok=True)
    out_path = os.path.join(policy_dir, f"policy_{target_date}.json")
    with open(out_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output


def replay_policy(start_date: str, end_date: str, symbols: list = None) -> dict:
    """回放模式: 从 start_date 到 end_date 逐日运行状态机"""
    if symbols is None:
        symbols = ETF_SYMBOLS

    from datetime import datetime
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()

    # 先清空所有状态
    for sym in symbols:
        pct_p80 = 1.5
        default = {
            "symbol": sym, "trend_state": "OUT", "exit_reason": None,
            "exit_date": None, "entry_date": None, "position_level": 0.0,
            "target_weight": 0.0, "peak_equity": 0.0, "pct_p80": pct_p80,
            "stop_warn_line": 8.0, "stop_exec_line": 12.0,
            "building_entry_low": None, "as_of": None, "history": []
        }
        save_state(default)

    current = start
    last_result = {}
    while current <= end:
        d = current.isoformat()
        lifecycle_path = os.path.join(ROOT, "data", "sector-lifecycle.json")
        warmup_path = os.path.join(ROOT, "data", "warmup", f"warmup-{d}-60.json")
        if not os.path.exists(warmup_path):
            warmup_path = os.path.join(ROOT, "data", "warmup", "warmup-60.json")

        if os.path.exists(lifecycle_path):
            last_result = run_policy_for_day(d, symbols, lifecycle_path, warmup_path)

        current += timedelta(days=1)

    return last_result


def main():
    parser = argparse.ArgumentParser(description="波段策略批量计算")
    parser.add_argument("--date", type=str, help="目标日期 YYYY-MM-DD, 默认今天")
    parser.add_argument("--replay", action="store_true", help="回放模式")
    parser.add_argument("--start", type=str, default="2025-06-01", help="回放起始日期")
    parser.add_argument("--symbols", type=str, help="逗号分隔的 symbol 列表")
    args = parser.parse_args()

    target_date = args.date or date.today().isoformat()
    symbols = args.symbols.split(",") if args.symbols else ETF_SYMBOLS

    if args.replay:
        result = replay_policy(args.start, target_date, symbols)
        print(f"回放完成: {args.start} → {target_date}")
        policies = result.get("policies", {})
        for sym, p in policies.items():
            print(f"  {sym}: {p['trend_state']} | {p['action']} | {p['reason'][:40]}")
    else:
        result = run_policy_for_day(target_date, symbols)
        print(f"策略计算完成: {target_date}")
        policies = result.get("policies", {})
        for sym, p in policies.items():
            print(f"  {sym}: {p['trend_state']} | {p['action']} | {p['reason'][:50]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
