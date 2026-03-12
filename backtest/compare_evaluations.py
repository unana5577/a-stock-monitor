#!/usr/bin/env python3
"""
对比简化版 vs 完整版评估逻辑

目标：
1. 运行简化版评估（只用分位数，忽略原始值）
2. 运行完整版评估（使用原始值 + 三层判断）
3. 对比准确率、信号分布
"""
import os
import sys
import json
import argparse
from typing import Dict, List
from datetime import datetime

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


def load_sector_data(etf_name: str, data_dir: str = "data"):
    """加载ETF数据"""
    path = f"{data_dir}/etf_daily/etf_backfill_2026-03-09.json"
    with open(path, "r") as f:
        data = json.load(f)

    sector_data = data.get(etf_name)
    if not sector_data:
        for key in data.keys():
            if etf_name in key or key in etf_name:
                sector_data = data[key]
                break

    records = []
    for record in sector_data.get("data", []):
        records.append({
            "date": pd.to_datetime(record.get("date")),
            "close": float(record.get("close", 0)),
            "amount": float(record.get("amount", 0)),
        })

    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def evaluate_simplified(metrics_list, future_days=3):
    """
    简化版评估：只用分位数，硬编码建议
    """
    correct = 0
    total = 0
    signals = {}

    for metrics in metrics_list[:-future_days]:
        alpha_5_q = metrics.get("alpha_5_q", 0.5)

        # 简化：只看Alpha_5分位数
        if alpha_5_q > 0.7:
            advice = "持股待涨"
        elif alpha_5_q > 0.5:
            advice = "持有"
        elif alpha_5_q < 0.3:
            advice = "观望"
        else:
            advice = "观望"

        future_return = metrics.get("future_return")
        if future_return is None:
            continue

        total += 1
        if advice in ["持股待涨", "持有"]:
            signals[advice] = signals.get(advice, {"correct": 0, "total": 0})
            signals[advice]["total"] += 1
            if future_return > 0:
                correct += 1
                signals[advice]["correct"] += 1

    accuracy = correct / total if total > 0 else 0
    return {
        "accuracy": accuracy,
        "total": total,
        "correct": correct,
        "signals": signals
    }


def evaluate_complete(metrics_list, future_days=3):
    """
    完整版评估：使用原始值 + 三层判断逻辑
    """
    correct = 0
    total = 0
    signals = {}
    signals_by_type = {
        "买入": {"correct": 0, "total": 0},
        "卖出": {"correct": 0, "total": 0},
        "观望": {"total": 0}
    }

    for i, metrics in enumerate(metrics_list[:-future_days]):
        # 提取原始指标
        alpha_5 = metrics.get("alpha_5", 0)
        close = metrics.get("close", 0)
        ma5 = metrics.get("ma5", close)
        ma5_slope = metrics.get("ma5_slope", 0)
        amount_share = metrics.get("amount_share", 0)
        amount_share_change = metrics.get("amount_share_change", 0)
        bias_20 = metrics.get("bias_20", 0)
        pct = metrics.get("pct", 0)

        # 三层判断
        momentum = determine_momentum(alpha_5, ma5_slope, close, ma5)

        amount_share_history = [m.get("amount_share", 0) for m in metrics_list[:i+1]]
        amount_share_high_20 = max(amount_share_history[-20:]) if len(amount_share_history) >= 20 else amount_share

        behavior = determine_fund_behavior(
            amount_share_pct=amount_share,
            amount_share_change=amount_share_change,
            amount_share_p80=None,
            amount_share_high_20=amount_share_high_20,
            bias_20=bias_20,
            pct=pct
        )

        advice = determine_advice(momentum, behavior)

        future_return = metrics.get("future_return")
        if future_return is None:
            continue

        total += 1

        # 统计
        signals[advice] = signals.get(advice, {"correct": 0, "total": 0})
        signals[advice]["total"] += 1

        if advice in ["持股待涨", "积极建仓", "低吸机会", "持有"]:
            signals_by_type["买入"]["total"] += 1
            if future_return > 0:
                correct += 1
                signals_by_type["买入"]["correct"] += 1
                signals[advice]["correct"] += 1
        elif advice in ["果断离场", "果断止损", "坚决回避"]:
            signals_by_type["卖出"]["total"] += 1
            if future_return < 0:
                correct += 1
                signals_by_type["卖出"]["correct"] += 1
                signals[advice]["correct"] += 1
        else:
            signals_by_type["观望"]["total"] += 1

    directional_total = signals_by_type["买入"]["total"] + signals_by_type["卖出"]["total"]
    accuracy = correct / directional_total if directional_total > 0 else 0

    return {
        "accuracy": accuracy,
        "total": directional_total,
        "correct": correct,
        "signals": signals,
        "signals_by_type": signals_by_type,
        "watch_total": signals_by_type["观望"]["total"]
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--etf", default="半导体", help="板块名称")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"对比评估: {args.etf}")
    print(f"{'='*60}\n")

    # 加载数据
    sector_df = load_sector_data(args.etf)
    print(f"数据点数: {len(sector_df)}")

    # 计算指标
    metrics_list = []
    for i in range(60, len(sector_df)):
        sector_cut = sector_df.iloc[:i+1].copy()

        # Alpha
        alpha_5 = calculate_alpha_n_days(
            list(zip(sector_cut["date"], sector_cut["close"])),
            list(zip(sector_cut["date"], sector_cut["close"])),
            days=5
        ) / 100  # 转换为比率
        alpha_20 = calculate_alpha_n_days(
            list(zip(sector_cut["date"], sector_cut["close"])),
            list(zip(sector_cut["date"], sector_cut["close"])),
            days=20
        ) / 100

        if alpha_5 is None:
            continue

        # 分位数
        historical_alpha5 = [m.get("alpha_5", 0) for m in metrics_list]
        if len(historical_alpha5) >= 20:
            alpha_5_q = sum(1 for x in historical_alpha5 if x < alpha_5) / len(historical_alpha5)
        else:
            alpha_5_q = 0.5

        # 价格指标
        close = sector_cut["close"].iloc[-1]
        ma5 = sector_cut["close"].rolling(5).mean().iloc[-1]
        ma5_slope = (sector_cut["close"].rolling(5).mean().iloc[-1] -
                     sector_cut["close"].rolling(5).mean().iloc[-6]) / 5 if len(sector_cut) >= 6 else 0

        # 资金指标
        amount_share = sector_cut["amount"].iloc[-1] / 1e12  # 简化
        amount_share_history = [m.get("amount_share", 0) for m in metrics_list]
        amount_share_ma5 = np.mean(amount_share_history[-5:]) if len(amount_share_history) >= 5 else amount_share
        amount_share_change = amount_share / amount_share_ma5 - 1 if amount_share_ma5 else 0

        # 乖离率
        ma20 = sector_cut["close"].rolling(20).mean().iloc[-1]
        bias_20 = (close - ma20) / ma20 * 100 if ma20 else 0

        # 涨跌
        pct = sector_cut["close"].pct_change().iloc[-1] * 100

        # 未来收益
        if i + 3 < len(sector_df):
            future_return = (sector_df["close"].iloc[i+3] - close) / close
        else:
            future_return = None

        metrics_list.append({
            "alpha_5": alpha_5,
            "alpha_20": alpha_20,
            "alpha_5_q": alpha_5_q,
            "close": close,
            "ma5": ma5 if not pd.isna(ma5) else close,
            "ma5_slope": ma5_slope,
            "amount_share": amount_share,
            "amount_share_ma5": amount_share_ma5,
            "amount_share_change": amount_share_change,
            "bias_20": bias_20,
            "pct": pct,
            "future_return": future_return
        })

    print(f"有效指标点数: {len(metrics_list)}\n")

    # 运行对比
    print("="*60)
    print("【简化版】只用分位数 + 硬编码建议")
    print("="*60)
    result_simplified = evaluate_simplified(metrics_list)
    print(f"准确率: {result_simplified['accuracy']:.2%}")
    print(f"信号总数: {result_simplified['total']}")
    print(f"信号分布: {result_simplified['signals']}\n")

    print("="*60)
    print("【完整版】原始值 + 三层判断逻辑")
    print("="*60)
    result_complete = evaluate_complete(metrics_list)
    print(f"准确率: {result_complete['accuracy']:.2%}")
    print(f"信号总数: {result_complete['total']}")
    print(f"信号类型: {result_complete['signals_by_type']}")
    print(f"观望信号: {result_complete['watch_total']}")
    print(f"各建议准确率:")
    for advice, stats in result_complete['signals'].items():
        acc = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
        print(f"  {advice}: {acc:.2%} ({stats['correct']}/{stats['total']})")
    print()

    # 对比总结
    print("="*60)
    print("【对比总结】")
    print("="*60)
    print(f"简化版准确率: {result_simplified['accuracy']:.2%} ({result_simplified['total']} 个信号)")
    print(f"完整版准确率: {result_complete['accuracy']:.2%} ({result_complete['total']} 个方向信号)")
    print(f"准确率提升: {(result_complete['accuracy'] - result_simplified['accuracy'])*100:.2f}个百分点")
    print(f"信号增加: {result_complete['total'] - result_simplified['total']} 个")


if __name__ == "__main__":
    main()
