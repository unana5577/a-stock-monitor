#!/usr/bin/env python3
"""
ETF数据加载模块
让系统能够使用回补的ETF数据
"""
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

def load_backfill_etf_data(sector_name=None):
    """
    加载回补的ETF数据

    Args:
        sector_name: 板块名称，如"半导体"。如果为None，返回所有板块

    Returns:
        DataFrame或dict: ETF数据
    """
    backfill_file = Path("data/etf_daily/etf_backfill_2026-03-09.json")

    if not backfill_file.exists():
        return None

    with open(backfill_file, 'r') as f:
        data = json.load(f)

    if sector_name:
        return data.get(sector_name)
    return data

def get_etf_dataframe(sector_name):
    """
    获取指定板块的ETF数据为DataFrame

    Args:
        sector_name: 板块名称

    Returns:
        DataFrame: 包含date, open, close, high, low, volume, amount
    """
    sector_data = load_backfill_etf_data(sector_name)

    if not sector_data or not sector_data.get('data'):
        return None

    df = pd.DataFrame(sector_data['data'])
    df['date'] = pd.to_datetime(df['date'])

    # 按日���排序
    df = df.sort_values('date')

    return df

def get_latest_etf_price(sector_name):
    """
    获取指定板块的最新价格

    Args:
        sector_name: 板块名称

    Returns:
        float: 最新收盘价，如果无数据返回None
    """
    sector_data = load_backfill_etf_data(sector_name)

    if not sector_data or not sector_data.get('data'):
        return None

    data = sector_data['data']
    if not data:
        return None

    return float(data[-1]['close'])

def get_etf_data_range(sector_name):
    """
    获取ETF数据的日期范围

    Args:
        sector_name: 板块名称

    Returns:
        tuple: (起始日期, 结束日期)
    """
    sector_data = load_backfill_etf_data(sector_name)

    if not sector_data or not sector_data.get('data'):
        return None, None

    data = sector_data['data']
    return data[0]['date'], data[-1]['date']

def get_all_etf_info():
    """
    获取所有ETF的信息

    Returns:
        dict: {板块名: {代码, 标准化代码, 数据范围, 条数}}
    """
    data = load_backfill_etf_data()

    if not data:
        return {}

    info = {}
    for sector, sector_data in data.items():
        info[sector] = {
            'code': sector_data.get('code'),
            'normalized_code': sector_data.get('normalized_code'),
            'start_date': sector_data.get('data', [{}])[0].get('date') if sector_data.get('data') else None,
            'end_date': sector_data.get('data', [{}])[-1].get('date') if sector_data.get('data') else None,
            'count': len(sector_data.get('data', []))
        }

    return info

# 测试代码
if __name__ == "__main__":
    print("=" * 80)
    print("ETF数据加载测试")
    print("=" * 80)

    # 测试1：获取所有ETF信息
    print("\n所有ETF信息:")
    info = get_all_etf_info()
    for sector, details in info.items():
        print(f"  {sector}: {details['code']} ({details['start_date']} 至 {details['end_date']}, {details['count']}天)")

    # 测试2：获取单个ETF数据
    print("\n半导体ETF数据示例:")
    df = get_etf_dataframe('半导体')
    if df is not None:
        print(df.head())
        print(f"\n数据形状: {df.shape}")
        print(f"列名: {list(df.columns)}")
    else:
        print("无数据")

    # 测试3：获取最新价格
    print("\n最新价格:")
    for sector in info.keys():
        price = get_latest_etf_price(sector)
        print(f"  {sector}: {price}")
