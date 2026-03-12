#!/usr/bin/env python3
"""动态基准选择 + 完整量价行为判断"""

import pandas as pd
import numpy as np
import json
import os

# ETF配置（移除硬编码基准）
ETF_LIST = [
    {"name": "半导体", "code": "512480", "file": "etf_512480.jsonl"},
    {"name": "云计算", "code": "516510", "file": "etf_516510.jsonl"},
    {"name": "新能源", "code": "516160", "file": "etf_516160.jsonl"},
    {"name": "有色金属", "code": "512400", "file": "etf_512400.jsonl"},
    {"name": "通讯设备", "code": "515880", "file": "etf_515880.jsonl"},
    {"name": "游戏", "code": "516010", "file": "etf_516010.jsonl"},
    {"name": "机器人", "code": "562500", "file": "etf_562500.jsonl"},
    {"name": "商业航天", "code": "563530", "file": "etf_563530.jsonl"},
]

# 基准配置
BENCHMARKS = {
    "上证": {"file": "index_000001.jsonl", "code": "000001"},
    "深证": {"file": "index_399001.jsonl", "code": "399001"},
    "创业板": {"file": "index_399006.jsonl", "code": "399006"},
    "科创板": {"file": "index_000688.jsonl", "code": "000688"},
}

def load_jsonl_data(file_path, date_from='2025-05-19'):
    """加载JSONL数据"""
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

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')

    if date_from:
        df = df[df['date'] >= date_from]

    return df

def select_daily_benchmark(etf_df, etf_date, benchmark_dfs, days=60):
    """为指定日期的ETF选择最佳基准

    Args:
        etf_df: ETF历史数据
        etf_date: 目标日期
        benchmark_dfs: 基准数据字典
        days: 计算相关性的天数

    Returns:
        (best_bench_name, correlation): 最佳基准名称和相关系数
    """
    # 获取目标日期之前的ETF历史数据
    etf_hist = etf_df[etf_df['date'] < etf_date].tail(days)

    if len(etf_hist) < 10:
        return None, None

    best_name = None
    best_corr = -1

    for bench_name, bench_info in BENCHMARKS.items():
        bench_df = benchmark_dfs.get(bench_name)
        if bench_df is None:
            continue

        # 获取对应日期的基准历史数据
        bench_hist = bench_df[bench_df['date'] < etf_date].tail(days)

        if len(bench_hist) < 10:
            continue

        # 合并计算相关性
        merged = pd.merge(
            etf_hist[['date', 'close']],
            bench_hist[['date', 'close']],
            on='date',
            how='inner',
            suffixes=('_etf', '_bench')
        )

        if len(merged) < 10:
            continue

        corr = merged['close_etf'].corr(merged['close_bench'])

        if corr is not None and corr > best_corr:
            best_corr = corr
            best_name = bench_name

    return best_name, best_corr

def calculate_volume_ratio(df, window=3):
    """计算量比"""
    df = df.copy()
    df['ma3_amount'] = df['amount'].rolling(window=window, min_periods=1).mean()
    df['volume_ratio'] = df['amount'] / df['ma3_amount']
    return df

def analyze_etf_dynamic_benchmark(etf_config, days=60):
    """使用动态基准分析ETF"""
    etf_name = etf_config['name']
    etf_code = etf_config['code']
    etf_file = f"data/etf_daily/{etf_config['file']}"

    print(f"\n{'='*100}")
    print(f"📊 {etf_name} ({etf_code}) - 动态基准选择")
    print(f"{'='*100}")

    # 加载ETF数据
    etf_df = load_jsonl_data(etf_file)
    if etf_df is None or len(etf_df) < days:
        print(f"❌ ETF数据不足")
        return None

    # 加载所有基准数据
    benchmark_dfs = {}
    for bench_name, bench_info in BENCHMARKS.items():
        bench_df = load_jsonl_data(f"data/index_daily/{bench_info['file']}")
        if bench_df is not None:
            benchmark_dfs[bench_name] = bench_df

    if not benchmark_dfs:
        print(f"❌ 基准数据缺失")
        return None

    # 计算量比
    etf_df = calculate_volume_ratio(etf_df)

    # 取最近days天
    etf_recent = etf_df.tail(days).copy()

    # 为每一天选择最佳基准
    results = []
    benchmark_stats = {}

    for _, row in etf_recent.iterrows():
        date = row['date']

        # 动态选择基准（基于该日期之前的60天数据）
        best_bench, corr = select_daily_benchmark(etf_df, date, benchmark_dfs, days=60)

        if best_bench is None:
            continue

        # 统计基准使用频率
        benchmark_stats[best_bench] = benchmark_stats.get(best_bench, 0) + 1

        # 获取基准涨跌幅
        bench_df = benchmark_dfs[best_bench]
        bench_row = bench_df[bench_df['date'] == date]

        if bench_row.empty:
            continue

        bench_row = bench_row.iloc[0]
        bench_pct = bench_row['pct']
        rel_strength = row['pct'] - bench_pct

        # 计算分位数（基于历史60天）
        hist = etf_df[etf_df['date'] < date].tail(60)
        if len(hist) < 20:
            continue

        hist = calculate_volume_ratio(hist)
        volume_ratio_80 = hist['volume_ratio'].quantile(0.8)
        volume_ratio_20 = hist['volume_ratio'].quantile(0.2)

        # 判断相对强度（直接比较，无阈值）
        if rel_strength > 0:
            rel_status = '��势'
        elif rel_strength < 0:
            rel_status = '弱于大盘'
        else:
            rel_status = '与大盘持平'

        # 判断量价行为
        if row['volume_ratio'] > volume_ratio_80:
            if row['pct'] > 0:
                if rel_status == '强于大盘':
                    behavior = "放量强势上涨"
                else:
                    behavior = "放量弱势上涨"
            elif row['pct'] < 0:
                if rel_status == '强于大盘' or rel_status == '与大盘持平':
                    behavior = "放量抗跌"
                else:
                    behavior = "放量下跌"
            else:
                behavior = "放量平盘"
        elif row['volume_ratio'] < volume_ratio_20:
            if row['pct'] > 0:
                if rel_status == '强于大盘':
                    behavior = "缩量强势上涨"
                else:
                    behavior = "缩量虚涨"
            elif row['pct'] < 0:
                if rel_status == '强于大盘':
                    behavior = "缩量抗跌"
                else:
                    behavior = "缩量下跌"
            else:
                behavior = "缩量平盘"
        else:
            behavior = "正常波动"

        results.append({
            'date': date.strftime('%Y-%m-%d'),
            'close': row['close'],
            'pct': row['pct'],
            'volume_ratio': row['volume_ratio'],
            'bench_name': best_bench,
            'bench_corr': corr,
            'bench_pct': bench_pct,
            'rel_strength': rel_strength,
            'rel_status': rel_status,
            'behavior': behavior
        })

    # 打印基准使用统计
    print(f"\n📈 基准使用统计（最近{days}天）:")
    for bench, count in sorted(benchmark_stats.items(), key=lambda x: x[1], reverse=True):
        pct = count / len(results) * 100 if results else 0
        print(f"  {bench}: {count}次 ({pct:.1f}%)")

    # 打印最近5天
    print(f"\n📋 最近5天量价行为（动态基准）:")
    print(f"{'日期':>12} {'收盘':>8} {'涨跌幅':>8} {'量比':>8} {'基准':>8} {'基准涨跌':>8} {'相对强度':>8} {'行为':>20}")
    print("-" * 110)

    for item in results[-5:][::-1]:
        print(f"{item['date']:>12} {item['close']:>8.3f} {item['pct']:>7.2f}% "
              f"{item['volume_ratio']:>8.2f} {item['bench_name']:>8} {item['bench_pct']:>7.2f}% "
              f"{item['rel_strength']:>7.2f}% {item['behavior']:>20}")

    return {
        'etf': etf_name,
        'code': etf_code,
        'benchmark_stats': benchmark_stats,
        'recent_data': results[-5:][::-1],
        'all_data': results
    }

def main():
    print("="*110)
    print("动态基准选择 + 量价行为判断回测")
    print("="*110)

    all_results = []

    for etf in ETF_LIST:
        result = analyze_etf_dynamic_benchmark(etf, days=60)
        if result:
            all_results.append(result)

    # 汇总基准使用情况
    print(f"\n\n{'='*110}")
    print("📊 所有ETF基准使用汇总")
    print(f"{'='*110}")

    print(f"\n{'ETF':>12} {'主要基准':>12} {'使用次数':>10} {'比例':>8}")
    print("-" * 60)

    for r in all_results:
        main_bench = max(r['benchmark_stats'].items(), key=lambda x: x[1])
        bench_name, count = main_bench
        pct = count / sum(r['benchmark_stats'].values()) * 100
        print(f"{r['etf']:>12} {bench_name:>12} {count:>10} {pct:>7.1f}%")

    # 分析最近3天（03-10至03-12）
    print(f"\n\n{'='*110}")
    print("📅 最近3天详细分析（03-10至03-12）")
    print(f"{'='*110}")

    target_dates = ['2026-03-10', '2026-03-11', '2026-03-12']

    for date in target_dates:
        print(f"\n{'='*110}")
        print(f"📅 {date}")
        print(f"{'='*110}")
        print(f"{'ETF':>12} {'涨跌幅':>8} {'基准':>8} {'基准涨跌':>8} {'相对强度':>8} {'行为':>20}")
        print("-" * 90)

        for r in all_results:
            for item in r['all_data']:
                if item['date'] == date:
                    print(f"{r['etf']:>12} {item['pct']:>7.2f}% {item['bench_name']:>8} "
                          f"{item['bench_pct']:>7.2f}% {item['rel_strength']:>7.2f}% {item['behavior']:>20}")
                    break

if __name__ == "__main__":
    main()
