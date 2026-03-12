#!/usr/bin/env python3
"""分析最新3天（03-10至03-12）的量价行为"""

import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta

# ETF配置
ETF_LIST = [
    {"name": "半导体", "code": "512480", "file": "etf_512480.jsonl", "benchmark": "index_000688.jsonl"},
    {"name": "云计算", "code": "516510", "file": "etf_516510.jsonl", "benchmark": "index_399006.jsonl"},
    {"name": "新能源", "code": "516160", "file": "etf_516160.jsonl", "benchmark": "index_399006.jsonl"},
    {"name": "有色金属", "code": "512400", "file": "etf_512400.jsonl", "benchmark": "index_000001.jsonl"},
    {"name": "通讯设备", "code": "515880", "file": "etf_515880.jsonl", "benchmark": "index_000001.jsonl"},
    {"name": "游戏", "code": "516010", "file": "etf_516010.jsonl", "benchmark": "index_399006.jsonl"},
    {"name": "机器人", "code": "562500", "file": "etf_562500.jsonl", "benchmark": "index_000688.jsonl"},
    {"name": "商业航天", "code": "563530", "file": "etf_563530.jsonl", "benchmark": "index_000688.jsonl"},
]

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

def calculate_volume_ratio(df, window=3):
    """计算量比"""
    df = df.copy()
    df['ma3_amount'] = df['amount'].rolling(window=window, min_periods=1).mean()
    df['volume_ratio'] = df['amount'] / df['ma3_amount']
    return df

def analyze_latest_days(etf_config, target_dates=['2026-03-10', '2026-03-11', '2026-03-12']):
    """分析指定日期的数据"""
    etf_name = etf_config['name']
    etf_file = f"data/etf_daily/{etf_config['file']}"
    bench_file = f"data/index_daily/{etf_config['benchmark']}"

    # 加载数据
    etf_df = load_jsonl_data(etf_file)
    bench_df = load_jsonl_data(bench_file)

    if etf_df is None or bench_df is None:
        return None

    # 合并数据
    merged = pd.merge(
        etf_df[['date', 'close', 'pct', 'amount', 'volume']],
        bench_df[['date', 'pct']],
        on='date',
        how='inner',
        suffixes=('', '_bench')
    )

    merged = calculate_volume_ratio(merged)

    # 计算分位数（基于过去60天）
    hist = merged.tail(60)
    volume_ratio_80 = hist['volume_ratio'].quantile(0.8)
    volume_ratio_20 = hist['volume_ratio'].quantile(0.2)

    # 提取目标日期的数据
    target_dates_dt = pd.to_datetime(target_dates)
    results = []

    for target_date in target_dates_dt:
        row = merged[merged['date'] == target_date]
        if row.empty:
            continue

        row = row.iloc[0]
        pct = row['pct']
        volume_ratio = row['volume_ratio']
        bench_pct = row['pct_bench']
        rel_strength = pct - bench_pct

        # 判断相对强度（直接比较，无阈值）
        if rel_strength > 0:
            rel_status = '强于大盘'
        elif rel_strength < 0:
            rel_status = '弱于大盘'
        else:
            rel_status = '与大盘持平'

        # 判断量价行为
        if volume_ratio > volume_ratio_80:
            if pct > 0:
                if rel_status == '强于大盘':
                    behavior = "放量强势上涨"
                else:
                    behavior = "放量弱势上涨"
            elif pct < 0:
                if rel_status == '强于大盘' or rel_status == '与大盘持平':
                    behavior = "放量抗跌"
                else:
                    behavior = "放量下跌"
            else:
                behavior = "放量平盘"
        elif volume_ratio < volume_ratio_20:
            if pct > 0:
                if rel_status == '强于大盘':
                    behavior = "缩量强势上涨"
                else:
                    behavior = "缩量虚涨"
            elif pct < 0:
                if rel_status == '强于大盘':
                    behavior = "缩量抗跌"
                else:
                    behavior = "缩量下跌"
            else:
                behavior = "缩量平盘"
        else:
            behavior = "正常波动"

        results.append({
            'date': row['date'].strftime('%Y-%m-%d'),
            'close': row['close'],
            'pct': pct,
            'volume_ratio': volume_ratio,
            'bench_pct': bench_pct,
            'rel_strength': rel_strength,
            'rel_status': rel_status,
            'behavior': behavior,
            'vr_80': volume_ratio_80,
            'vr_20': volume_ratio_20
        })

    return {
        'etf': etf_name,
        'code': etf_config['code'],
        'results': results
    }

def main():
    print("="*120)
    print("📊 最新3天量价行为分析（2026-03-10 至 2026-03-12）")
    print("="*120)

    all_results = []

    for etf in ETF_LIST:
        result = analyze_latest_days(etf)
        if result and result['results']:
            all_results.append(result)

    # 按日期展示
    target_dates = ['2026-03-10', '2026-03-11', '2026-03-12']

    for date in target_dates:
        print(f"\n{'='*120}")
        print(f"📅 {date} 量价行为汇总")
        print(f"{'='*120}")
        print(f"{'ETF':>12} {'收盘':>8} {'涨跌幅':>8} {'量比':>8} {'基准涨跌':>8} {'相对强度':>8} {'资金行为':>20}")
        print("-" * 120)

        for r in all_results:
            for item in r['results']:
                if item['date'] == date:
                    print(f"{r['etf']:>12} {item['close']:>8.3f} {item['pct']:>7.2f}% "
                          f"{item['volume_ratio']:>8.2f} {item['bench_pct']:>7.2f}% "
                          f"{item['rel_strength']:>7.2f}% {item['behavior']:>20}")

    # 横向对比表格
    print(f"\n\n{'='*120}")
    print("📊 3天横向对比")
    print(f"{'='*120}")

    for r in all_results:
        print(f"\n## {r['etf']} ({r['code']})")
        print(f"{'日期':>12} {'行为':>20} {'涨跌幅':>8} {'量比':>8} {'相对强度':>8} {'说明':>30}")
        print("-" * 120)

        for item in r['results']:
            note = ""
            if '放量' in item['behavior']:
                note += f"量比>{item['vr_80']:.2f}(80分位) "
            elif '缩量' in item['behavior']:
                note += f"量比<{item['vr_20']:.2f}(20分位) "

            if item['rel_status'] == '强势':
                note += "跑赢基准"
            elif item['rel_status'] == '弱势':
                note += "跑输基准"

            print(f"{item['date']:>12} {item['behavior']:>20} {item['pct']:>7.2f}% "
                  f"{item['volume_ratio']:>8.2f} {item['rel_strength']:>7.2f}% {note:>30}")

    # 统计信号
    print(f"\n\n{'='*120}")
    print("📈 信号统计")
    print(f"{'='*120}")

    signal_stats = {}
    date_signal_stats = {d: {} for d in target_dates}

    for r in all_results:
        for item in r['results']:
            behavior = item['behavior']
            signal_stats[behavior] = signal_stats.get(behavior, 0) + 1
            date_signal_stats[item['date']][behavior] = date_signal_stats[item['date']].get(behavior, 0) + 1

    print("\n整体信号分布:")
    for behavior, count in sorted(signal_stats.items(), key=lambda x: x[1], reverse=True):
        pct = count / len([r for r in all_results for item in r['results']]) * 100
        print(f"  {behavior}: {count}次 ({pct:.1f}%)")

    print("\n每日信号分布:")
    for date in target_dates:
        print(f"\n  {date}:")
        day_stats = date_signal_stats[date]
        total = sum(day_stats.values())
        for behavior, count in sorted(day_stats.items(), key=lambda x: x[1], reverse=True):
            pct = count / total * 100 if total > 0 else 0
            print(f"    {behavior}: {count}次 ({pct:.1f}%)")

if __name__ == "__main__":
    main()
