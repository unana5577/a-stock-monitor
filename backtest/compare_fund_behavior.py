#!/usr/bin/env python3
"""对比资金行为判断：绝对值方案 vs 分位数方案"""
import os
import sys
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sector_lifecycle import determine_fund_behavior

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


def evaluate_fund_behavior(etf_name, use_quantile=True):
    """评估资金行为判断方案"""
    df = load_sector_data(etf_name)

    if len(df) < 60:
        return None

    # 计算成交占比历史数据
    amount_share_series = []
    for i in range(len(df)):
        amount_share_series.append(df["amount"].iloc[i])

    # 计算历史 Amount_Share_Change
    historical_changes = []
    for i in range(5, len(amount_share_series)):
        ma5 = np.mean(amount_share_series[max(0, i-5):i+1])
        if ma5 > 0:
            change = amount_share_series[i] / ma5 - 1
            historical_changes.append(change)

    # 计算80分位
    amount_share_change_q80 = float(pd.Series(historical_changes).quantile(0.8)) if len(historical_changes) >= 20 else None

    behavior_dist = {}
    volume_start_count = 0

    for i in range(60, min(len(df), 300)):
        sector_cut = df.iloc[:i+1]

        # 计算指标
        close = sector_cut["close"].iloc[-1]
        ma20 = sector_cut["close"].rolling(20).mean().iloc[-1]
        bias_20 = (close - ma20) / ma20 * 100 if ma20 else 0
        pct = sector_cut["close"].pct_change().iloc[-1] * 100

        # 计算 Amount_Share_Change
        amount_share_current = amount_share_series[i]
        amount_share_ma5 = np.mean(amount_share_series[max(0, i-5):i+1])
        amount_share_change = amount_share_current / amount_share_ma5 - 1 if amount_share_ma5 > 0 else None

        amount_share_high_20 = max(amount_share_series[max(0, i-19):i+1])
        amount_share_p80 = float(pd.Series(amount_share_series[:i]).quantile(0.8)) if len(amount_share_series[:i]) >= 20 else None

        # 判断
        if use_quantile:
            behavior = determine_fund_behavior(
                amount_share_pct=amount_share_current,
                amount_share_change=amount_share_change,
                amount_share_p80=amount_share_p80,
                amount_share_high_20=amount_share_high_20,
                bias_20=bias_20,
                pct=pct,
                amount_share_change_q80=amount_share_change_q80
            )
        else:
            behavior = determine_fund_behavior(
                amount_share_pct=amount_share_current,
                amount_share_change=amount_share_change,
                amount_share_p80=amount_share_p80,
                amount_share_high_20=amount_share_high_20,
                bias_20=bias_20,
                pct=pct,
                amount_share_change_q80=None
            )

        behavior_dist[behavior] = behavior_dist.get(behavior, 0) + 1
        if behavior == "放量启动":
            volume_start_count += 1

    return {
        "behavior_dist": behavior_dist,
        "volume_start_count": volume_start_count,
        "total": len(range(60, min(len(df), 300)))
    }


def main():
    print(f"\n{'='*80}")
    print(f"{'ETF':<12} {'方案':<12} {'放量启动':<12} {'资金撤退':<12} {'横盘整理':<12}")
    print(f"{'='*80}")

    for etf in ETF_LIST:
        # 绝对值方案
        result_abs = evaluate_fund_behavior(etf, use_quantile=False)
        # 分位数方案
        result_q = evaluate_fund_behavior(etf, use_quantile=True)

        if not result_abs or not result_q:
            continue

        print(f"{etf:<12} 绝对值方案   {result_abs['volume_start_count']:<12} {result_abs['behavior_dist'].get('资金撤退', 0):<12} {result_abs['behavior_dist'].get('横盘整理', 0):<12}")
        print(f"{etf:<12} 分位数方案   {result_q['volume_start_count']:<12} {result_q['behavior_dist'].get('资金撤退', 0):<12} {result_q['behavior_dist'].get('横盘整理', 0):<12}")
        print()


if __name__ == "__main__":
    main()
