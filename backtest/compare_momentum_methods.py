#!/usr/bin/env python3
"""
对比动能判断：文档版 vs 分位数版

目标：验证分位数方案是否优于文档的绝对值方案
"""
import os
import sys
import json
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from sector_lifecycle import (
    determine_momentum,
    determine_fund_behavior,
    determine_advice,
    calculate_amount_share_ma5,
)


ETF_LIST = ["半导体", "云计算", "新能源", "商业航天", "创新药", "有色金属", "通讯设备"]


def load_sector_data(etf_name: str):
    """加载ETF数据"""
    path = "data/etf_daily/etf_backfill_2026-03-09.json"
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


def determine_momentum_document(alpha_5_pct, ma5_slope, close, ma5):
    """文档版：绝对值阈值"""
    a = alpha_5_pct

    if a > 3 and ma5_slope > 0 and close > ma5:
        return "强势向上"
    if a > 3 and ma5_slope < 0 and close < ma5:
        return "强势向下"
    if 1 <= a <= 3 and ma5_slope > 0 and close > ma5:
        return "偏强向上"
    if 1 <= a <= 3 and ma5_slope < 0 and close < ma5:
        return "偏强向下"
    if -1 <= a <= 1:
        return "中性震荡"
    if a < -1 and ma5_slope < 0 and close < ma5:
        return "弱势向下"
    if a < -1 and ma5_slope > 0 and close > ma5:
        return "弱势反弹"
    return "中性震荡" if close > ma5 else "弱势向下"


def determine_momentum_quantile(alpha_5_pct, ma5_slope, close, ma5, alpha_5_q70, alpha_5_q50):
    """分位数版：使用分位数阈值"""
    # 分位数判断
    if alpha_5_pct > 0:  # 正收益
        if alpha_5_q70 is not None and alpha_5_q70 > 0.7:  # 70%分位 > 0.7%
            threshold_high = np.percentile([alpha_5_q70], 80) if isinstance(alpha_5_q70, list) else alpha_5_q70
        else:
            threshold_high = 2.76  # 从数据统计得出

        if alpha_5_pct > threshold_high and ma5_slope > 0 and close > ma5:
            return "强势向上"
        elif alpha_5_pct > 1 and ma5_slope > 0 and close > ma5:
            return "偏强向上"
        else:
            return "中性震荡"
    else:
        return "中性震荡"


def evaluate_method(etf_name, use_quantile=True):
    """评估单个ETF"""
    df = load_sector_data(etf_name)

    momentum_dist = {}
    signals = {"买入": 0, "卖出": 0, "观望": 0}
    directional_signals = 0

    for i in range(60, min(len(df), 300)):
        sector_cut = df.iloc[:i+1]

        # 计算5日收益率（代替Alpha_5）
        ret_5 = (sector_cut["close"].iloc[-1] - sector_cut["close"].iloc[-6]) / sector_cut["close"].iloc[-6] * 100 if len(sector_cut) >= 6 else 0
        alpha_5_pct = ret_5

        # 计算分位数
        historical_returns = []
        for j in range(60, i+1):
            if j >= 5:
                ret = (df["close"].iloc[j] - df["close"].iloc[j-5]) / df["close"].iloc[j-5] * 100
                historical_returns.append(ret)

        alpha_5_q70 = np.percentile(historical_returns, 70) if len(historical_returns) >= 20 else None
        alpha_5_q50 = np.percentile(historical_returns, 50) if len(historical_returns) >= 20 else None

        # 计算其他指标
        close = sector_cut["close"].iloc[-1]
        ma5 = sector_cut["close"].rolling(5).mean().iloc[-1]
        ma5_slope = (sector_cut["close"].rolling(5).mean().iloc[-1] - sector_cut["close"].rolling(5).mean().iloc[-6]) / 5 if len(sector_cut) >= 6 else 0

        amount_share = sector_cut["amount"].iloc[-1]
        amount_share_history = [df["amount"].iloc[j] for j in range(max(0, i-19), i+1)]
        amount_share_high_20 = max(amount_share_history) if amount_share_history else amount_share
        amount_share_change = 0  # 简化

        bias_20 = 0  # 简化
        pct = (sector_cut["close"].iloc[-1] - sector_cut["close"].iloc[-2]) / sector_cut["close"].iloc[-2] * 100 if len(sector_cut) >= 2 else 0

        # 动能判断
        if use_quantile:
            momentum = determine_momentum_quantile(alpha_5_pct, ma5_slope, close, ma5, alpha_5_q70, alpha_5_q50)
        else:
            momentum = determine_momentum_document(alpha_5_pct, ma5_slope, close, ma5)

        momentum_dist[momentum] = momentum_dist.get(momentum, 0) + 1

        # 资金行为（简化）
        if amount_share_change > 0.5 and pct > 0:
            behavior = "放量启动"
        elif amount_share < amount_share_high_20 * 0.8:
            behavior = "资金撤退"
        else:
            behavior = "横盘整理"

        # 操作建议
        advice = determine_advice(momentum, behavior)

        if advice in ["持股待涨", "积极建仓", "低吸机会", "持有"]:
            signals["买入"] += 1
            directional_signals += 1
        elif advice in ["果断离场", "果断止损", "坚决回避"]:
            signals["卖出"] += 1
            directional_signals += 1
        else:
            signals["观望"] += 1

    return {
        "momentum_dist": momentum_dist,
        "signals": signals,
        "directional_rate": directional_signals / len(range(60, min(len(df), 300))) if len(df) > 60 else 0
    }


def main():
    print(f"\n{'='*80}")
    print(f"{'ETF':<12} {'方案':<12} {'方向信号率':<12} {'买入':<6} {'卖出':<6} {'观望':<6}")
    print(f"{'='*80}")

    for etf in ETF_LIST:
        # 文档版
        result_doc = evaluate_method(etf, use_quantile=False)
        doc_rate = f"{result_doc['directional_rate']:.1%}"

        # 分位数版
        result_q = evaluate_method(etf, use_quantile=True)
        q_rate = f"{result_q['directional_rate']:.1%}"

        print(f"{etf:<12} 文档版     {doc_rate:<12} {result_doc['signals']['买入']:<6} {result_doc['signals']['卖出']:<6} {result_doc['signals']['观望']:<6}")
        print(f"{etf:<12} 分位数版   {q_rate:<12} {result_q['signals']['买入']:<6} {result_q['signals']['卖出']:<6} {result_q['signals']['观望']:<6}")
        print()


if __name__ == "__main__":
    main()
