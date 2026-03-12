#!/usr/bin/env python3
"""测试不同分位数阈值的信号分布"""

import pandas as pd
import numpy as np
import json
import os

ETF_LIST = [
    {"name": "半导体", "file": "etf_512480.jsonl"},
    {"name": "云计算", "file": "etf_516510.jsonl"},
    {"name": "新能源", "file": "etf_516160.jsonl"},
    {"name": "有色金属", "file": "etf_512400.jsonl"},
    {"name": "通讯设备", "file": "etf_515880.jsonl"},
    {"name": "游戏", "file": "etf_516010.jsonl"},
    {"name": "机器人", "file": "etf_562500.jsonl"},
    {"name": "商业航天", "file": "etf_563530.jsonl"},
]

def load_etf_data(file_path):
    """加载ETF数据"""
    if not os.path.exists(file_path):
        return None

    rows = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                rows.append(data)
            except:
                continue

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df = df[df['date'] >= '2025-05-19']
    return df

def calculate_volume_ratio(df, window=3):
    """计算量比"""
    df = df.copy()
    df['ma3_amount'] = df['amount'].rolling(window=window, min_periods=1).mean()
    df['volume_ratio'] = df['amount'] / df['ma3_amount']
    return df

def test_thresholds(etf_name, file_path):
    """测试不同分位数阈值"""
    df = load_etf_data(f"data/etf_daily/{file_path}")
    if df is None or len(df) < 60:
        return None

    df = calculate_volume_ratio(df)
    df = df.tail(60)  # 最近60天

    # 计算不同分位数
    quantiles = [15, 20, 25, 30, 70, 75, 80, 85]
    results = {}

    for q in quantiles:
        results[f'p{q}'] = df['volume_ratio'].quantile(q/100)

    # 统计量比分布
    stats = {
        'mean': df['volume_ratio'].mean(),
        'std': df['volume_ratio'].std(),
        'min': df['volume_ratio'].min(),
        'max': df['volume_ratio'].max(),
        'median': df['volume_ratio'].median(),
    }

    # 测试不同阈值组合的信号分布
    threshold_pairs = [(70, 30), (75, 25), (80, 20), (85, 15)]

    signal_counts = {}
    for high_q, low_q in threshold_pairs:
        high_threshold = df['volume_ratio'].quantile(high_q/100)
        low_threshold = df['volume_ratio'].quantile(low_q/100)

        signals = {
            '放量': ((df['volume_ratio'] > high_threshold).sum()),
            '缩量': ((df['volume_ratio'] < low_threshold).sum()),
            '正常': ((df['volume_ratio'] >= low_threshold) & (df['volume_ratio'] <= high_threshold)).sum()
        }

        signal_counts[f'{high_q}/{low_q}'] = {
            'high_threshold': round(high_threshold, 2),
            'low_threshold': round(low_threshold, 2),
            'signals': signals,
            '放量比例': f"{signals['放量']/len(df)*100:.1f}%",
            '缩量比例': f"{signals['缩量']/len(df)*100:.1f}%",
        }

    return {
        'etf': etf_name,
        'stats': stats,
        'quantiles': results,
        'signal_counts': signal_counts,
    }

def main():
    print("="*100)
    print("量比分位数阈值测试")
    print("="*100)

    all_results = []

    for etf in ETF_LIST:
        result = test_thresholds(etf['name'], etf['file'])
        if result:
            all_results.append(result)

    # 打印每个ETF的分位数分布
    print(f"\n{'='*100}")
    print("📊 各ETF量比分位数分布（基于最近60天）")
    print(f"{'='*100}")

    for r in all_results:
        print(f"\n## {r['etf']}")
        print(f"  均值: {r['stats']['mean']:.2f}, 标准差: {r['stats']['std']:.2f}, 中位数: {r['stats']['median']:.2f}")
        print(f"  最小值: {r['stats']['min']:.2f}, 最大值: {r['stats']['max']:.2f}")
        print(f"  分位数:")
        for q in [15, 20, 25, 30, 70, 75, 80, 85]:
            print(f"    {q}分位: {r['quantiles'][f'p{q}']:.2f}")

    # 对比不同阈值组合的信号分布
    print(f"\n{'='*100}")
    print("📊 不同阈值组合的信号分布对比")
    print(f"{'='*100}")

    for pair in ['70/30', '75/25', '80/20', '85/15']:
        print(f"\n## {pair} 分位阈值")
        print(f"{'ETF':>12} {'高阈值':>8} {'低阈值':>8} {'放量天数':>10} {'缩量天数':>10} {'正常天数':>10} {'放量%':>8} {'缩量%':>8}")
        print("-" * 100)

        for r in all_results:
            data = r['signal_counts'][pair]
            print(f"{r['etf']:>12} {data['high_threshold']:>8} {data['low_threshold']:>8} "
                  f"{data['signals']['放量']:>10} {data['signals']['缩量']:>10} {data['signals']['正常']:>10} "
                  f"{data['放量比例']:>8} {data['缩量比例']:>8}")

    # 分析：每个ETF应该用什么阈值
    print(f"\n{'='*100}")
    print("💡 建议：每个ETF的个性化阈值")
    print(f"{'='*100}")

    print(f"\n说明：根据波动特性，不同ETF可能需要不同的阈值")
    print(f"- 波动大的ETF（如半导体、游戏）：可以考虑75/25或80/20")
    print(f"- 波动小的ETF（如有色金属、通讯设备）：可以考虑70/30或75/25")
    print(f"\n请根据上方信号分布的合理性（放量/缩量比例是否适中）来选择阈值")

if __name__ == "__main__":
    main()
