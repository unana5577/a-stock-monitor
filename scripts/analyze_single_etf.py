#!/usr/bin/env python3
"""
详细分析单个ETF的乖离率状态
"""

import pandas as pd
import json
from pathlib import Path

DATA_DIR = Path("data/etf_daily")

def analyze_etf_detail(etf_name, etf_code, filename):
    """详细分析单个ETF"""
    filepath = DATA_DIR / filename

    # 加载数据
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))

    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    # 计算乖离率
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['bias_5'] = (df['close'] - df['ma5']) / df['ma5'] * 100

    # ���算分位数
    df['bias_5_95'] = df['bias_5'].rolling(window=60).quantile(0.95)
    df['bias_5_80'] = df['bias_5'].rolling(window=60).quantile(0.80)
    df['bias_5_60'] = df['bias_5'].rolling(window=60).quantile(0.60)
    df['bias_5_40'] = df['bias_5'].rolling(window=60).quantile(0.40)
    df['bias_5_20'] = df['bias_5'].rolling(window=60).quantile(0.20)
    df['bias_5_05'] = df['bias_5'].rolling(window=60).quantile(0.05)

    # 最新数据
    latest = df.iloc[-1]

    print(f"\n{'='*80}")
    print(f"📊 {etf_name} ({etf_code}) - {latest['date'].strftime('%Y-%m-%d')}")
    print(f"{'='*80}")

    print(f"\n📍 当前状态:")
    print(f"   收盘价: {latest['close']}")
    print(f"   MA5: {latest['ma5']:.3f}")
    print(f"   Bias_5: {latest['bias_5']:.2f}%")

    print(f"\n📊 过去60天Bias_5分位数:")
    print(f"   95%分位: {latest['bias_5_95']:.2f}%")
    print(f"   80%分位: {latest['bias_5_80']:.2f}%")
    print(f"   60%分位: {latest['bias_5_60']:.2f}%")
    print(f"   40%分位: {latest['bias_5_40']:.2f}%")
    print(f"   20%分位: {latest['bias_5_20']:.2f}%")
    print(f"   5%分位:  {latest['bias_5_05']:.2f}%")

    print(f"\n📈 最近30天的Bias_5走势:")
    recent_30 = df.tail(30)[['date', 'close', 'bias_5']].copy()
    for _, row in recent_30.iterrows():
        print(f"   {row['date'].strftime('%m-%d')}: 收盘{row['close']:.3f}, Bias_5={row['bias_5']:.2f}%")

    print(f"\n💰 价格位置（52周高低点）:")
    min_52w = df.tail(252)['close'].min()
    max_52w = df.tail(252)['close'].max()
    current = latest['close']
    position = (current - min_52w) / (max_52w - min_52w) * 100
    print(f"   52周最高: {max_52w:.3f}")
    print(f"   52周最低: {min_52w:.3f}")
    print(f"   当前价格: {current:.3f}")
    print(f"   位置: {position:.1f}%")

    # 风险等级判断
    bias = latest['bias_5']
    if bias > latest['bias_5_95']:
        level = "极度风险"
    elif bias > latest['bias_5_80']:
        level = "高风险"
    elif bias > latest['bias_5_60']:
        level = "中高位风险"
    elif bias > latest['bias_5_40']:
        level = "中低位机会"
    elif bias > latest['bias_5_20']:
        level = "低风险机会"
    else:
        level = "极度机会"

    print(f"\n⚠️  当前风险等级: {level}")

# 分析机器人和创新药
print("\n" + "="*80)
print("机器人详细分析")
print("="*80)
analyze_etf_detail("机器人", "562500", "etf_562500.jsonl")

print("\n" + "="*80)
print("创新药详细分析")
print("="*80)
analyze_etf_detail("创新药", "515120", "etf_515120.jsonl")
