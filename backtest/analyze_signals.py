#!/usr/bin/env python3
"""
分析指标分布，找出为什么没有方向性信号
"""
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from sector_lifecycle import (
    determine_momentum,
    determine_fund_behavior,
    determine_advice,
    calculate_alpha_n_days,
    calculate_amount_share_ma5,
)


def analyze_sector(etf_name="半导体"):
    """分析单个ETF的指标��布"""
    path = "data/etf_daily/etf_backfill_2026-03-09.json"
    with open(path, "r") as f:
        data = json.load(f)

    sector_data = data.get(etf_name)
    records = []
    for record in sector_data.get("data", []):
        records.append({
            "date": pd.to_datetime(record.get("date")),
            "close": float(record.get("close", 0)),
            "amount": float(record.get("amount", 0)),
        })

    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)

    print(f"\n{'='*60}")
    print(f"分析: {etf_name}")
    print(f"{'='*60}\n")

    momentum_dist = {}
    behavior_dist = {}
    advice_dist = {}

    # 计算历史 5 日收益率（用于分位数计算）
    historical_returns = []
    for j in range(60, len(df)):
        if j >= 5:
            ret = (df["close"].iloc[j] - df["close"].iloc[j-5]) / df["close"].iloc[j-5] * 100
            historical_returns.append(ret)

    # 计算历史 Amount_Share_Change
    amount_share_series = df["amount"].tolist()
    historical_amount_changes = []
    for j in range(5, len(amount_share_series)):
        ma5 = np.mean(amount_share_series[max(0, j-5):j+1])
        if ma5 > 0:
            change = amount_share_series[j] / ma5 - 1
            historical_amount_changes.append(change)

    amount_share_change_q80 = float(pd.Series(historical_amount_changes).quantile(0.8)) if len(historical_amount_changes) >= 20 else None

    for i in range(60, len(df)):
        sector_cut = df.iloc[:i+1].copy()

        # 使用 5 日收益率代替 Alpha（因为没有基准）
        ret_5 = (sector_cut["close"].iloc[-1] - sector_cut["close"].iloc[-6]) / sector_cut["close"].iloc[-6] * 100 if len(sector_cut) >= 6 else 0
        alpha_5 = ret_5 / 100  # 转为小数

        # 计算分位数位置
        alpha_5_q = None
        if len(historical_returns) >= 20 and i > 60:
            alpha_5_q = sum(1 for x in historical_returns[:i-60] if x < ret_5) / len(historical_returns[:i-60])

        if alpha_5 is None:
            continue

        close = sector_cut["close"].iloc[-1]
        ma5 = sector_cut["close"].rolling(5).mean().iloc[-1]
        ma5_slope = (sector_cut["close"].rolling(5).mean().iloc[-1] - sector_cut["close"].rolling(5).mean().iloc[-6]) / 5 if len(sector_cut) >= 6 else 0

        amount_share = sector_cut["amount"].iloc[-1]
        amount_share_history_full = [df["amount"].iloc[j] for j in range(max(0, i-19), i+1)]
        amount_share_high_20 = max(amount_share_history_full) if amount_share_history_full else amount_share

        # 计算 Amount_Share_Change
        amount_share_ma5 = np.mean(amount_share_history_full[-5:]) if len(amount_share_history_full) >= 5 else amount_share
        amount_share_change = amount_share / amount_share_ma5 - 1 if amount_share_ma5 > 0 else 0

        # 计算 Amount_Share_P80
        amount_share_p80 = float(pd.Series(amount_share_series[:i]).quantile(0.8)) if len(amount_share_series[:i]) >= 20 else None

        ma20 = sector_cut["close"].rolling(20).mean().iloc[-1]
        bias_20 = (close - ma20) / ma20 * 100 if ma20 else 0
        pct = sector_cut["close"].pct_change().iloc[-1] * 100

        # 判断（传入分位数）
        momentum = determine_momentum(alpha_5, ma5_slope, close, ma5, alpha_5_q)

        behavior = determine_fund_behavior(
            amount_share_pct=amount_share,
            amount_share_change=amount_share_change,
            amount_share_p80=amount_share_p80,
            amount_share_high_20=amount_share_high_20,
            bias_20=bias_20,
            pct=pct,
            amount_share_change_q80=amount_share_change_q80
        )

        advice = determine_advice(momentum, behavior)

        momentum_dist[momentum] = momentum_dist.get(momentum, 0) + 1
        behavior_dist[behavior] = behavior_dist.get(behavior, 0) + 1
        advice_dist[advice] = advice_dist.get(advice, 0) + 1

    # 输出分布
    print("【动能分布】")
    for k, v in sorted(momentum_dist.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} ({v/sum(momentum_dist.values())*100:.1f}%)")

    print("\n【资金行为分布】")
    for k, v in sorted(behavior_dist.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} ({v/sum(behavior_dist.values())*100:.1f}%)")

    print("\n【操作建议分布】")
    for k, v in sorted(advice_dist.items(), key=lambda x: -x[1]):
        is_directional = "✅方向" if k in ["持股待涨", "积极建仓", "低吸机会", "果断离场", "果断止损", "坚决回避", "分批止盈", "逐步减仓"] else "⭕观望"
        print(f"  {is_directional} {k}: {v} ({v/sum(advice_dist.values())*100:.1f}%)")

    # 分析原因
    print(f"\n【原因分析】")
    directional_count = sum(v for k, v in advice_dist.items() if k in ["持股待涨", "积极建仓", "低吸机会", "果断离场", "果断止损", "坚决回避", "分批止盈", "逐步减仓"])
    print(f"方向性信号数: {directional_count}/{sum(advice_dist.values())}")
    print(f"观望信号数: {sum(advice_dist.values()) - directional_count}/{sum(advice_dist.values())}")

    # 检查关键组合
    buy_signals = ["持股待涨", "积极建仓", "低吸机会"]
    sell_signals = ["果断离场", "果断止损", "坚决回避"]

    print(f"\n【买入信号条件】")
    print(f"  '强势向上' + '放量启动' → '持股待涨'")
    print(f"  '偏强向上' + '放量启动' → '积极建仓'")
    print(f"  当前实际分布:")
    print(f"    强势向上数量: {momentum_dist.get('强势向上', 0)}")
    print(f"    放量启动数量: {behavior_dist.get('放量启动', 0)}")
    print(f"    偏强向上数量: {momentum_dist.get('偏强向上', 0)}")


if __name__ == "__main__":
    analyze_sector("半导体")
