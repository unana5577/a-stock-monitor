#!/usr/bin/env python3
"""测试量价行为判断 - 使用ETF数据"""

import pandas as pd
import numpy as np
import json
from datetime import datetime
import os

# ETF配置（基于data/etf_daily/目录）
ETF_LIST = [
    {"name": "半导体", "code": "512480", "file": "etf_512480.jsonl", "benchmark": "科创板"},
    {"name": "云计算", "code": "516510", "file": "etf_516510.jsonl", "benchmark": "创业板"},
    {"name": "新能源", "code": "516160", "file": "etf_516160.jsonl", "benchmark": "创业板"},
    {"name": "有色金属", "code": "512400", "file": "etf_512400.jsonl", "benchmark": "上证"},
    {"name": "通讯设备", "code": "515880", "file": "etf_515880.jsonl", "benchmark": "上证"},
    {"name": "游戏", "code": "516010", "file": "etf_516010.jsonl", "benchmark": "创业板"},
    {"name": "机器人", "code": "562500", "file": "etf_562500.jsonl", "benchmark": "科创板"},
    {"name": "商业航天", "code": "563530", "file": "etf_563530.jsonl", "benchmark": "科创板"},
]

def load_etf_data(file_path, days=60):
    """加载ETF数据从JSONL文件"""
    try:
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

        # 过滤从2025-05-19开始的数据
        df = df[df['date'] >= '2025-05-19']

        if len(df) < days:
            print(f"  ⚠️  数据量不足: {len(df)}天 < {days}天")
            return None

        return df.tail(days)
    except Exception as e:
        print(f"  ❌ 加载失败: {e}")
        return None

def load_benchmark_data(benchmark_name, days=60):
    """加载基准数据从sector-cache"""
    benchmark_map = {
        "上证": {"code": "sh000001", "sector": "上证"},
        "深证": {"code": "sz399001", "sector": "深证"},
        "创业板": {"code": "sz399006", "sector": "创业板"},
        "科创板": {"code": "000688", "sector": "科创板"}
    }

    if benchmark_name not in benchmark_map:
        return None

    bench_config = benchmark_map[benchmark_name]

    try:
        # 优先从sector-cache加载
        cache_file = 'data/sector-cache.csv'
        if os.path.exists(cache_file):
            df = pd.read_csv(cache_file)
            bench_df = df[df['sector'] == bench_config['sector']]
            if not bench_df.empty:
                bench_df['date'] = pd.to_datetime(bench_df['date'])
                bench_df = bench_df.sort_values('date')

                # 过滤从2025-05-19开始
                bench_df = bench_df[bench_df['date'] >= '2025-05-19']

                return bench_df.tail(days)[['date', 'pct', 'close']]
        return None
    except Exception as e:
        return None

def calculate_volume_ratio(df, window=3):
    """计算量比 = 当日成交额 / MA3"""
    if len(df) < window:
        return df

    df = df.copy()
    df['ma3_amount'] = df['amount'].rolling(window=window, min_periods=1).mean()
    df['volume_ratio'] = df['amount'] / df['ma3_amount']
    return df

def analyze_volume_price_behavior(etf_name, code, file_path, benchmark_name):
    """分析单个ETF的量价行为"""
    print(f"\n{'='*60}")
    print(f"📊 {etf_name} ({code}) - 基准: {benchmark_name}")
    print(f"{'='*60}")

    # 加载数据
    etf_df = load_etf_data(file_path, days=60)
    if etf_df is None:
        print("❌ 基础数据不全")
        return None

    # 加载基准
    bench_df = load_benchmark_data(benchmark_name, days=60)
    if bench_df is None or bench_df.empty:
        print("⚠️  基准数据缺失，无法计算相对强度")
        etf_df['bench_pct'] = 0
        etf_df['relative_strength'] = etf_df['pct']
        has_benchmark = False
    else:
        etf_df = pd.merge(
            etf_df,
            bench_df[['date', 'pct']],
            on='date',
            how='left',
            suffixes=('', '_bench')
        )
        etf_df['bench_pct'] = etf_df['pct_bench'].fillna(0)
        etf_df['relative_strength'] = etf_df['pct'] - etf_df['bench_pct']
        has_benchmark = True

    # 计算量比
    etf_df = calculate_volume_ratio(etf_df, window=3)

    # 计算分位数（基于历史60天）
    volume_ratio_80 = etf_df['volume_ratio'].quantile(0.8)
    volume_ratio_20 = etf_df['volume_ratio'].quantile(0.2)

    print(f"\n📈 量比分位数:")
    print(f"  80分位(放量): {volume_ratio_80:.2f}")
    print(f"  20分位(缩量): {volume_ratio_20:.2f}")
    print(f"  数据范围: {etf_df['date'].min().strftime('%Y-%m-%d')} ~ {etf_df['date'].max().strftime('%Y-%m-%d')}")
    print(f"  数据量: {len(etf_df)}天")

    # 判断最近5天的量价行为
    recent = etf_df.tail(5).copy()
    recent = recent.sort_values('date', ascending=False)

    print(f"\n📋 最近5天量价行为:")
    print(f"{'日期':>12} {'收盘':>8} {'涨跌幅':>8} {'量比':>8} {'相对强度':>8} {'资金行为':>30}")
    print("-" * 90)

    results = []

    for _, row in recent.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        close = row['close']
        pct = row['pct']
        volume_ratio = row['volume_ratio']
        relative_strength = row['relative_strength']

        # 判断量价行为
        behavior = "正常波动"
        if pd.notna(volume_ratio):
            if volume_ratio > volume_ratio_80:
                if pct > 0:
                    behavior = "量价齐升(资金进场)"
                elif relative_strength > 1:
                    behavior = f"放量抗跌(洗盘/吸筹)"
                else:
                    behavior = "放量下跌(资金出逃)"
            elif volume_ratio < volume_ratio_20:
                if pct > 0:
                    behavior = "缩量上涨(虚涨)"
                else:
                    behavior = "缩量下跌(观望)"
            else:
                behavior = "正常波动"

        print(f"{date_str:>12} {close:>8.3f} {pct:>7.2f}% {volume_ratio:>8.2f} {relative_strength:>7.2f}% {behavior:>30}")

        results.append({
            "date": date_str,
            "close": close,
            "pct": pct,
            "volume_ratio": volume_ratio,
            "relative_strength": relative_strength,
            "behavior": behavior
        })

    return {
        "etf": etf_name,
        "code": code,
        "benchmark": benchmark_name,
        "volume_ratio_80": volume_ratio_80,
        "volume_ratio_20": volume_ratio_20,
        "recent_data": results,
        "data_status": "完整",
        "has_benchmark": has_benchmark
    }

def main():
    print("="*90)
    print("量价行为判断测试（基于ETF数据，从2025-05-19开始）")
    print("="*90)

    all_results = []
    missing_data = []

    for etf in ETF_LIST:
        file_path = f"data/etf_daily/{etf['file']}"
        result = analyze_volume_price_behavior(
            etf["name"],
            etf["code"],
            file_path,
            etf["benchmark"]
        )

        if result:
            all_results.append(result)
        else:
            missing_data.append(f"{etf['name']} ({etf['code']})")

    # 汇总
    print(f"\n\n{'='*90}")
    print("📊 汇总统计")
    print(f"{'='*90}")

    print(f"\n✅ 数据完整的ETF ({len(all_results)}个):")
    for r in all_results:
        bench_status = f"基准: {r['benchmark']}" if r['has_benchmark'] else "基准缺失"
        print(f"  - {r['etf']}: 量比80分位={r['volume_ratio_80']:.2f}, 20分位={r['volume_ratio_20']:.2f}, {bench_status}")

    if missing_data:
        print(f"\n❌ 数据不全的ETF ({len(missing_data)}个):")
        for m in missing_data:
            print(f"  - {m}")

    # 生成验证表格
    print(f"\n\n{'='*90}")
    print("📋 详细验证表格（请核对以下日期的走势）")
    print(f"{'='*90}")

    for r in all_results:
        print(f"\n## {r['etf']} ({r['code']}) - 基准: {r['benchmark']}")
        print(f"{'日期':>12} {'行为':>30} {'涨跌幅':>8} {'量比':>8} {'相对强度':>8}")
        print("-" * 90)
        for item in r['recent_data']:
            print(f"{item['date']:>12} {item['behavior']:>30} {item['pct']:>7.2f}% {item['volume_ratio']:>8.2f} {item['relative_strength']:>7.2f}%")

if __name__ == "__main__":
    main()
