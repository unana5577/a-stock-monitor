#!/usr/bin/env python3
"""调试分位数计算"""
import os
import sys
import json
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sector_lifecycle import calculate_alpha_n_days, determine_momentum

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

# 计算历史 Alpha_5 分布
historical_alpha5 = []
for i in range(60, min(250, len(df))):
    sector_cut = df.iloc[:i+1]
    if len(sector_cut) >= 6:
        ret_5 = (sector_cut["close"].iloc[-1] - sector_cut["close"].iloc[-6]) / sector_cut["close"].iloc[-6] * 100
        historical_alpha5.append(ret_5)

print(f"历史 Alpha_5 样本数: {len(historical_alpha5)}")
print(f"范围: {min(historical_alpha5):.2f}% ~ {max(historical_alpha5):.2f}%")
print(f"70% 分位: {pd.Series(historical_alpha5).quantile(0.7):.2f}%")

# 测试最后一天
sector_cut = df.iloc[:min(250, len(df))]
ret_5 = (sector_cut["close"].iloc[-1] - sector_cut["close"].iloc[-6]) / sector_cut["close"].iloc[-6] * 100

# 计算分位数位置
alpha_5_q = sum(1 for x in historical_alpha5 if x < ret_5) / len(historical_alpha5)

print(f"\n当前 Alpha_5: {ret_5:.2f}%")
print(f"当前分位数位置: {alpha_5_q:.2%}")

# 测试动能判断
close = sector_cut["close"].iloc[-1]
ma5 = sector_cut["close"].rolling(5).mean().iloc[-1]
ma5_slope = (sector_cut["close"].rolling(5).mean().iloc[-1] - sector_cut["close"].rolling(5).mean().iloc[-6]) / 5

print(f"\n技术指标:")
print(f"收盘价: {close:.2f}")
print(f"MA5: {ma5:.2f}")
print(f"MA5斜率: {ma5_slope:.4f}")
print(f"价格 > MA5: {close > ma5}")

# 测试新函数
momentum_q = determine_momentum(ret_5/100, ma5_slope, close, ma5, alpha_5_q)
momentum_abs = determine_momentum(ret_5/100, ma5_slope, close, ma5)

print(f"\n动能判断结果:")
print(f"分位数方案: {momentum_q}")
print(f"绝对值方案: {momentum_abs}")
