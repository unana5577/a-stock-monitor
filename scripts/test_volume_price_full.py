#!/usr/bin/env python3
"""测试完整量价行为判断（包含相对强度）"""

import pandas as pd
import numpy as np
import json
import os

# ETF配置
ETF_LIST = [
    {"name": "半导体", "code": "512480", "file": "etf_512480.jsonl", "benchmark": "index_000688.jsonl"},  # 科创板
    {"name": "云计算", "code": "516510", "file": "etf_516510.jsonl", "benchmark": "index_399006.jsonl"},  # 创业板
    {"name": "新能源", "code": "516160", "file": "etf_516160.jsonl", "benchmark": "index_399006.jsonl"},  # 创业板
    {"name": "有色金属", "code": "512400", "file": "etf_512400.jsonl", "benchmark": "index_000001.jsonl"},  # 上证
    {"name": "通讯设备", "code": "515880", "file": "etf_515880.jsonl", "benchmark": "index_000001.jsonl"},  # 上证
    {"name": "游戏", "code": "516010", "file": "etf_516010.jsonl", "benchmark": "index_399006.jsonl"},  # 创业板
    {"name": "机器人", "code": "562500", "file": "etf_562500.jsonl", "benchmark": "index_000688.jsonl"},  # 科创板
    {"name": "商业航天", "code": "563530", "file": "etf_563530.jsonl", "benchmark": "index_000688.jsonl"},  # 科创板
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

    # 过滤日期
    if date_from:
        df = df[df['date'] >= date_from]

    return df

def calculate_volume_ratio(df, window=3):
    """计算量比"""
    df = df.copy()
    df['ma3_amount'] = df['amount'].rolling(window=window, min_periods=1).mean()
    df['volume_ratio'] = df['amount'] / df['ma3_amount']
    return df

def calculate_relative_strength(etf_pct, bench_pct, method='percentile'):
    """判断相对强度

    Args:
        etf_pct: ETF涨跌幅
        bench_pct: 基准涨跌幅
        method: 'percentile'使用分位数, 'fixed'使用固定阈值
    """
    rel_strength = etf_pct - bench_pct

    if method == 'fixed':
        if rel_strength > 1:
            return '强势'
        elif rel_strength < -1:
            return '弱势'
        else:
            return '持平'

    elif method == 'percentile':
        # 分位数判断（需要历史数据，这里先用固定阈值代替）
        if rel_strength > 1:
            return '强势'
        elif rel_strength < -1:
            return '弱势'
        else:
            return '持平'

    return '持平'

def determine_volume_price_behavior(row, volume_ratio_80, volume_ratio_20, method='fixed'):
    """判断量价行为

    Args:
        row: 数据行
        volume_ratio_80: 量比80分位
        volume_ratio_20: 量比20分位
        method: relative_strength判断方法
    """
    pct = row['pct']
    volume_ratio = row['volume_ratio']
    bench_pct = row.get('bench_pct', 0)

    # 判断相对强度（直接比较，无阈值）
    rel_strength = pct - bench_pct
    if rel_strength > 0:
        rel_status = '强于大盘'
    elif rel_strength < 0:
        rel_status = '弱于大盘'
    else:
        rel_status = '与大盘持平'

    # 量价行为判断
    behavior = ""
    if pd.notna(volume_ratio):
        if volume_ratio > volume_ratio_80:
            if pct > 0:
                if rel_status == '强于大盘':
                    behavior = "放量强势上涨(资金强力进场)"
                else:
                    behavior = "放量弱势上涨(跑输基准)"
            elif pct < 0:
                if rel_status == '强于大盘' or rel_status == '与大盘持平':
                    behavior = "放量抗跌(洗盘/吸筹)"
                else:
                    behavior = "放量下跌(恐慌出逃)"
            else:
                behavior = "放量平盘(观望)"

        elif volume_ratio < volume_ratio_20:
            if pct > 0:
                if rel_status == '强于大盘':
                    behavior = "缩量强势上涨(惜售)"
                else:
                    behavior = "缩量虚涨(谨慎)"
            elif pct < 0:
                if rel_status == '强于大盘':
                    behavior = "缩量抗跌(可能企稳)"
                else:
                    behavior = "缩量下跌(观望)"
            else:
                behavior = "缩量平盘(观望)"
        else:
            behavior = "正常波动"

    return {
        'behavior': behavior,
        'rel_strength': rel_strength,
        'rel_status': rel_status
    }

def analyze_etf(etf_config, days=60):
    """分析单个ETF"""
    etf_name = etf_config['name']
    etf_code = etf_config['code']
    etf_file = f"data/etf_daily/{etf_config['file']}"
    bench_file = f"data/index_daily/{etf_config['benchmark']}"

    print(f"\n{'='*80}")
    print(f"📊 {etf_name} ({etf_code}) - 基准: {etf_config['benchmark']}")
    print(f"{'='*80}")

    # 加载ETF数据
    etf_df = load_jsonl_data(etf_file)
    if etf_df is None or len(etf_df) < days:
        print(f"❌ ETF数据不足: {len(etf_df) if etf_df is not None else 0}天")
        return None

    # 加载基准数据
    bench_df = load_jsonl_data(bench_file)
    if bench_df is None:
        print(f"⚠️  基准数据缺失")
        return None

    # 合并数据
    merged = pd.merge(
        etf_df[['date', 'close', 'pct', 'amount', 'volume']],
        bench_df[['date', 'pct']],
        on='date',
        how='inner',
        suffixes=('', '_bench')
    )

    if len(merged) < days:
        print(f"⚠️  合并后数据不足: {len(merged)}天")
        return None

    merged = calculate_volume_ratio(merged)
    merged = merged.tail(days)

    # 计算分位数
    volume_ratio_80 = merged['volume_ratio'].quantile(0.8)
    volume_ratio_20 = merged['volume_ratio'].quantile(0.2)

    print(f"\n📈 量比分位数:")
    print(f"  80分位(放量): {volume_ratio_80:.2f}")
    print(f"  20分位(缩量): {volume_ratio_20:.2f}")
    print(f"  数据范围: {merged['date'].min().strftime('%Y-%m-%d')} ~ {merged['date'].max().strftime('%Y-%m-%d')}")
    print(f"  数据量: {len(merged)}天")

    # 判断最近5天
    recent = merged.tail(5).copy()
    recent = recent.sort_values('date', ascending=False)

    print(f"\n📋 最近5天量价行为（包含相对强度）:")
    print(f"{'日期':>12} {'收盘':>8} {'涨跌幅':>8} {'量比':>8} {'相对强度':>10} {'资金行为':>35}")
    print("-" * 100)

    results = []

    for _, row in recent.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        result = determine_volume_price_behavior(row, volume_ratio_80, volume_ratio_20)

        print(f"{date_str:>12} {row['close']:>8.3f} {row['pct']:>7.2f}% "
              f"{row['volume_ratio']:>8.2f} {result['rel_strength']:>9.2f}% "
              f"{result['behavior']:>35}")

        results.append({
            "date": date_str,
            "close": row['close'],
            "pct": row['pct'],
            "volume_ratio": row['volume_ratio'],
            "rel_strength": result['rel_strength'],
            "rel_status": result['rel_status'],
            "behavior": result['behavior']
        })

    return {
        "etf": etf_name,
        "code": etf_code,
        "benchmark": etf_config['benchmark'],
        "volume_ratio_80": volume_ratio_80,
        "volume_ratio_20": volume_ratio_20,
        "recent_data": results,
        "data_status": "完整"
    }

def main():
    print("="*100)
    print("完整量价行为判断测试（包含相对强度）")
    print("相对强度阈值: ±1% (ETF涨跌幅 - 基准涨跌幅)")
    print("="*100)

    all_results = []

    for etf in ETF_LIST:
        result = analyze_etf(etf, days=60)
        if result:
            all_results.append(result)

    # 汇总
    print(f"\n\n{'='*100}")
    print("📊 汇总统计")
    print(f"{'='*100}")

    print(f"\n✅ 数据完整的ETF ({len(all_results)}个):")
    for r in all_results:
        print(f"  - {r['etf']}: 量比80分位={r['volume_ratio_80']:.2f}, 20分位={r['volume_ratio_20']:.2f}")

    # 统计信号分布
    print(f"\n📊 最近5天信号分布:")
    signal_counts = {}
    for r in all_results:
        for item in r['recent_data']:
            behavior = item['behavior']
            signal_counts[behavior] = signal_counts.get(behavior, 0) + 1

    for behavior, count in sorted(signal_counts.items(), key=lambda x: x[1], reverse=True):
        pct = count / (len(all_results) * 5) * 100
        print(f"  {behavior}: {count}次 ({pct:.1f}%)")

    # 生成验证表格
    print(f"\n\n{'='*100}")
    print("📋 详细验证表格（请核对以下日期的走势）")
    print(f"{'='*100}")

    for r in all_results:
        print(f"\n## {r['etf']} ({r['code']})")
        print(f"{'日期':>12} {'相对强度':>10} {'行为':>35} {'涨跌幅':>8} {'量比':>8}")
        print("-" * 100)
        for item in r['recent_data']:
            print(f"{item['date']:>12} {item['rel_strength']:>9.2f}% "
                  f"{item['behavior']:>35} {item['pct']:>7.2f}% {item['volume_ratio']:>8.2f}")

if __name__ == "__main__":
    main()
