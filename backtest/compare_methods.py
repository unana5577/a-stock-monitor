#!/usr/bin/env python3
"""
对比文档方案 vs 分位数方案

文档方案：使用0306文档定义的绝对值阈值
分位数方案：使用分位数阈值

对比指标：
1. 方向性信号数量（买入+卖出）
2. 准确率
3. 各类建议的分布
"""
import os
import sys
import json
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


ETF_LIST = [
    "半导体", "云计算", "新能源", "商业航天", "创新药", "有色金属", "通讯设备"
]


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


def evaluate_document_method(metrics_list, future_days=3):
    """
    文档方案：使用绝对值阈值（0306文档定义）

    位置判断（5.1节）：
    - Alpha_20 > 8% 且 Amount_Share_MA5 > 0.5% = 高位区
    - Alpha_20 > 4% 且 Amount_Share_MA5 > 0.4% = 中高位区
    - ...
    """
    correct = 0
    total = 0
    signals = {}
    signals_by_type = {"买入": {"total": 0, "correct": 0}, "卖出": {"total": 0, "correct": 0}, "观望": {"total": 0}}

    for i, metrics in enumerate(metrics_list[:-future_days]):
        alpha_5 = metrics.get("alpha_5", 0) * 100  # 转百分比
        alpha_20 = metrics.get("alpha_20", 0) * 100
        amount_share_ma5 = metrics.get("amount_share_ma5", 0) * 100
        close = metrics.get("close", 0)
        ma5 = metrics.get("ma5", close)
        ma5_slope = metrics.get("ma5_slope", 0) * 100  # 转百分比
        amount_share = metrics.get("amount_share", 0) * 100
        amount_share_change = metrics.get("amount_share_change", 0) * 100
        bias_20 = metrics.get("bias_20", 0)
        pct = metrics.get("pct", 0)

        # === 文档定义的绝对值判断 ===

        # 动能判断（5.2节）：使用原始值
        momentum = determine_momentum(alpha_5/100, ma5_slope/100, close, ma5)

        # 资金行为判断（5.3节）：使用绝对值
        amount_share_history = [m.get("amount_share", 0) for m in metrics_list[:i+1]]
        amount_share_high_20 = max(amount_share_history[-20:]) if len(amount_share_history) >= 20 else amount_share

        behavior = determine_fund_behavior(
            amount_share_pct=amount_share/100,
            amount_share_change=amount_share_change/100,
            amount_share_p80=None,
            amount_share_high_20=amount_share_high_20/100,
            bias_20=bias_20,
            pct=pct
        )

        # 操作建议（6.1节映射表）
        advice = determine_advice(momentum, behavior)

        future_return = metrics.get("future_return")
        if future_return is None:
            continue

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
        "directional_signals": directional_total,
        "correct": correct,
        "signals": signals,
        "signals_by_type": signals_by_type,
        "watch_total": signals_by_type["观望"]["total"]
    }


def evaluate_quantile_method(metrics_list, future_days=3):
    """
    分位数方案：使用分位数阈值

    位置判断：
    - Alpha_20 > 80%分位 且 Amount_Share_MA5 > 80%分位 = 高位区
    """
    correct = 0
    total = 0
    signals = {}
    signals_by_type = {"买入": {"total": 0, "correct": 0}, "卖出": {"total": 0, "correct": 0}, "观望": {"total": 0}}

    for i, metrics in enumerate(metrics_list[:-future_days]):
        # 提取分位数
        alpha_5_q = metrics.get("alpha_5_q", 0.5)
        alpha_20_q = metrics.get("alpha_20_q", 0.5)
        amount_share_q = metrics.get("amount_share_q", 0.5)

        # 提取原始值
        alpha_5 = metrics.get("alpha_5", 0)
        close = metrics.get("close", 0)
        ma5 = metrics.get("ma5", close)
        ma5_slope = metrics.get("ma5_slope", 0)
        amount_share = metrics.get("amount_share", 0)
        amount_share_change = metrics.get("amount_share_change", 0)
        bias_20 = metrics.get("bias_20", 0)
        pct = metrics.get("pct", 0)

        # === 分位数判断 ===

        # 动能：Alpha_5分位数 + 斜率
        if alpha_5_q > 0.7 and ma5_slope > 0 and close > ma5:
            momentum = "强势向上"
        elif alpha_5_q > 0.5 and ma5_slope > 0:
            momentum = "偏强向上"
        elif alpha_5_q < 0.3 and ma5_slope < 0 and close < ma5:
            momentum = "弱势向下"
        elif alpha_5_q < 0.3:
            momentum = "弱势反弹"
        else:
            momentum = "中性震荡"

        # 资金行为：使用原始值（这部分保持不变）
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
        "directional_signals": directional_total,
        "correct": correct,
        "signals": signals,
        "signals_by_type": signals_by_type,
        "watch_total": signals_by_type["观望"]["total"]
    }


def prepare_metrics(sector_df):
    """准备指标数据"""
    metrics_list = []

    for i in range(60, len(sector_df)):
        sector_cut = sector_df.iloc[:i+1].copy()

        # Alpha
        alpha_5 = calculate_alpha_n_days(
            list(zip(sector_cut["date"], sector_cut["close"])),
            list(zip(sector_cut["date"], sector_cut["close"])),
            days=5
        ) / 100
        alpha_20 = calculate_alpha_n_days(
            list(zip(sector_cut["date"], sector_cut["close"])),
            list(zip(sector_cut["date"], sector_cut["close"])),
            days=20
        ) / 100

        if alpha_5 is None:
            continue

        # 计算分位数
        historical_alpha5 = [m.get("alpha_5", 0) for m in metrics_list]
        historical_alpha20 = [m.get("alpha_20", 0) for m in metrics_list]
        historical_amount = [m.get("amount_share", 0) for m in metrics_list]

        alpha_5_q = sum(1 for x in historical_alpha5 if x < alpha_5) / len(historical_alpha5) if len(historical_alpha5) >= 20 else 0.5
        alpha_20_q = sum(1 for x in historical_alpha20 if x < alpha_20) / len(historical_alpha20) if len(historical_alpha20) >= 20 else 0.5
        amount_share_q = sum(1 for x in historical_amount if x < (sector_cut["amount"].iloc[-1] if len(sector_cut) > 0 else 0)) / len(historical_amount) if len(historical_amount) >= 20 else 0.5

        # 价格指标
        close = sector_cut["close"].iloc[-1]
        ma5 = sector_cut["close"].rolling(5).mean().iloc[-1]
        ma5_slope = (sector_cut["close"].rolling(5).mean().iloc[-1] - sector_cut["close"].rolling(5).mean().iloc[-6]) / 5 if len(sector_cut) >= 6 else 0

        # 资金指标
        amount_share = sector_cut["amount"].iloc[-1]
        amount_share_history = [m.get("amount_share", 0) for m in metrics_list]
        amount_share_ma5 = np.mean(amount_share_history[-5:]) if len(amount_share_history) >= 5 else amount_share
        amount_share_change = amount_share / amount_share_ma5 - 1 if amount_share_ma5 else 0

        # 乖离率
        ma20 = sector_cut["close"].rolling(20).mean().iloc[-1]
        bias_20 = (close - ma20) / ma20 * 100 if ma20 else 0

        # 涨跌
        pct = sector_cut["close"].pct_change().iloc[-1] * 100

        # 未来收益
        future_return = (sector_df["close"].iloc[i+3] - close) / close if i + 3 < len(sector_df) else None

        metrics_list.append({
            "alpha_5": alpha_5,
            "alpha_20": alpha_20,
            "alpha_5_q": alpha_5_q,
            "alpha_20_q": alpha_20_q,
            "amount_share_q": amount_share_q,
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

    return metrics_list


def main():
    print(f"\n{'='*80}")
    print(f"{'ETF':<12} {'方案':<12} {'准确率':<10} {'方向信号':<10} {'观望':<10}")
    print(f"{'='*80}")

    summary = {
        "document_method": {"accuracy_sum": 0, "signals_sum": 0, "count": 0},
        "quantile_method": {"accuracy_sum": 0, "signals_sum": 0, "count": 0}
    }

    for etf_name in ETF_LIST:
        print(f"\n处理: {etf_name}")
        sector_df = load_sector_data(etf_name)
        metrics_list = prepare_metrics(sector_df)

        if len(metrics_list) < 50:
            print(f"  跳过（数据不足: {len(metrics_list)}）")
            continue

        # 文档方案
        result_doc = evaluate_document_method(metrics_list)
        summary["document_method"]["accuracy_sum"] += result_doc["accuracy"]
        summary["document_method"]["signals_sum"] += result_doc["directional_signals"]
        summary["document_method"]["count"] += 1

        # 分位数方案
        result_quantile = evaluate_quantile_method(metrics_list)
        summary["quantile_method"]["accuracy_sum"] += result_quantile["accuracy"]
        summary["quantile_method"]["signals_sum"] += result_quantile["directional_signals"]
        summary["quantile_method"]["count"] += 1

        # 输出对比
        acc_doc = f"{result_doc['accuracy']:.1%}" if result_doc['directional_signals'] > 0 else "N/A"
        acc_q = f"{result_quantile['accuracy']:.1%}" if result_quantile['directional_signals'] > 0 else "N/A"

        print(f"  {etf_name:<12} 文档方案     {acc_doc:<10} {result_doc['directional_signals']:<10} {result_doc['watch_total']:<10}")
        print(f"  {etf_name:<12} 分位数方案   {acc_q:<10} {result_quantile['directional_signals']:<10} {result_quantile['watch_total']:<10}")

    # 总结
    print(f"\n{'='*80}")
    print("【总结对比】")
    print(f"{'='*80}")

    doc_avg_acc = summary["document_method"]["accuracy_sum"] / summary["document_method"]["count"] if summary["document_method"]["count"] > 0 else 0
    doc_avg_signals = summary["document_method"]["signals_sum"] / summary["document_method"]["count"] if summary["document_method"]["count"] > 0 else 0

    q_avg_acc = summary["quantile_method"]["accuracy_sum"] / summary["quantile_method"]["count"] if summary["quantile_method"]["count"] > 0 else 0
    q_avg_signals = summary["quantile_method"]["signals_sum"] / summary["quantile_method"]["count"] if summary["quantile_method"]["count"] > 0 else 0

    print(f"文档方案（绝对值）：平均准确率 {doc_avg_acc:.1%}，平均方向信号数 {doc_avg_signals:.1f}")
    print(f"分位数方案：      平均准确率 {q_avg_acc:.1%}，平均方向信号数 {q_avg_signals:.1f}")
    print(f"\n准确率差异: {(q_avg_acc - doc_avg_acc)*100:+.1f}个百分点")
    print(f"信号数量差异: {q_avg_signals - doc_avg_signals:+.1f}个")

    # 结论
    if summary["document_method"]["signals_sum"] == 0:
        print(f"\n⚠️  警告：文档方案在所有ETF上都未产生方向性信号！")
        print(f"   这说明文档定义的绝对值阈值可能过于严格（如Alpha>8%不可达）")
        print(f"   建议：使用分位数方案或调整阈值")
    elif q_avg_signals > doc_avg_signals * 2:
        print(f"\n📊 分位数方案产生的信号明显多于文档方案")
        print(f"   但需要权衡：信号多≠准确率高，需要结合实际使用场景")
    else:
        print(f"\n✓ 两种方案都能产生有效信号，可根据需求选择")


if __name__ == "__main__":
    main()
