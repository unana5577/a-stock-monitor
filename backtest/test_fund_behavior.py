#!/usr/bin/env python3
"""测试资金行为判断：绝对值方案 vs 分位数方案"""
import os
import sys
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sector_lifecycle import determine_fund_behavior

# 加载数据
path = "data/etf_daily/etf_backfill_2026-03-09.json"
with open(path, "r") as f:
    data = json.load(f)

sector_data = data["半导体"]
records = []
for record in sector_data.get("data", []):
    records.append({
        "date": pd.to_datetime(record.get("date")),
        "close": float(record.get("close", 0)),
        "amount": float(record.get("amount", 0)),
    })

df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)

# 计算成交占比历史数据
amount_share_series = []
for i in range(len(df)):
    # 简化：直接用成交额作为代理
    amount_share_series.append(df["amount"].iloc[i])

# 计算历史 Amount_Share_Change
historical_changes = []
for i in range(5, len(amount_share_series)):
    ma5 = np.mean(amount_share_series[max(0, i-5):i+1])
    if ma5 > 0:
        change = amount_share_series[i] / ma5 - 1
        historical_changes.append(change)

# 计算80分位
amount_share_change_q80 = float(pd.Series(historical_changes).quantile(0.8))

print(f"历史 Amount_Share_Change 样本数: {len(historical_changes)}")
print(f"范围: {min(historical_changes):.4f} ~ {max(historical_changes):.4f}")
print(f"80分位: {amount_share_change_q80:.4f}")
print(f"绝对值阈值: 0.5")
print()

# 测试场景
test_cases = [
    {"change": 0.6, "pct": 2.0, "desc": "高增长率"},
    {"change": 0.4, "pct": 2.0, "desc": "中等增长率"},
    {"change": 0.1, "pct": 2.0, "desc": "低增长率"},
    {"change": -0.2, "pct": -5.0, "desc": "负增长"},
]

print(f"{'场景':<12} {'变化率':<10} {'绝对值方案':<15} {'分位数方案':<15}")
print("=" * 60)

for case in test_cases:
    result_abs = determine_fund_behavior(
        amount_share_pct=0.5,
        amount_share_change=case["change"],
        amount_share_p80=None,
        amount_share_high_20=None,
        bias_20=0,
        pct=case["pct"],
        amount_share_change_q80=None  # 绝对值方案
    )

    result_q = determine_fund_behavior(
        amount_share_pct=0.5,
        amount_share_change=case["change"],
        amount_share_p80=None,
        amount_share_high_20=None,
        bias_20=0,
        pct=case["pct"],
        amount_share_change_q80=amount_share_change_q80  # 分位数方案
    )

    print(f"{case['desc']:<12} {case['change']:<10.2f} {result_abs:<15} {result_q:<15}")
