#!/usr/bin/env python3
"""
带日期验证的分时数据pct计算
"""

import os
import json
from datetime import datetime, timedelta

def get_latest_file(pattern):
    """获取最新的文件"""
    files = []
    for f in os.listdir('data/minute'):
        if pattern in f and f.endswith('.jsonl'):
            files.append(f)

    if not files:
        return None

    # 按日期排序，找到最新的
    files.sort(reverse=True)
    return files[0]

def get_latest_daily_file(code):
    """获取最新的日线文件"""
    daily_file = f'data/index_daily/index_{code}.jsonl'
    if not os.path.exists(daily_file):
        return None

    with open(daily_file, 'r') as f:
        lines = f.readlines()

    if not lines:
        return None

    # 获取最后一条数据
    latest = json.loads(lines[-1])
    return latest

def calculate_pct(current, prev_close):
    """计算涨跌幅"""
    if prev_close and prev_close != 0:
        return round((current - prev_close) / prev_close * 100, 2)
    return None

def verify_large_cap_with_date():
    """验证大盘指数（带日期验证）"""
    print("=== 大盘指数分时数据pct计算（带日期验证）===")

    # 获取最新的上证分时文件
    latest_file = get_latest_file('sse')
    if not latest_file:
        print("❌ 未找到上证分时文件")
        return

    print(f"使用分时文件: {latest_file}")

    # 提取日期
    date_str = latest_file.split('-')[2].split('.')[0]
    if date_str.isdigit() and len(date_str) == 8:
        file_date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
    else:
        file_date = "未知"
    current_date = datetime.now().strftime('%Y-%m-%d')

    print(f"分时数据日期: {file_date}")
    print(f"当前日期: {current_date}")

    # 判断是否是今天的数据
    if file_date != current_date:
        print("⚠️ 分时数据不是今天的，使用日线昨收")
        # 使用昨收价计算
        latest_daily = get_latest_daily_file('000001')
        if latest_daily:
            prev_close = latest_daily['close']
            print(f"使用日线昨收: {prev_close}")
        else:
            prev_close = 3957.05  # 默认值
    else:
        # 获取昨天的收盘价
        yesterday_daily = get_latest_daily_file('000001')
        if yesterday_daily:
            prev_close = yesterday_daily['close']
            print(f"使用昨日收盘: {prev_close}")
        else:
            prev_close = 3957.05

    # 读取分时数据
    with open(f'data/minute/{latest_file}', 'r') as f:
        lines = f.readlines()

    print(f"\n分时数据条数: {len(lines)}")
    print("\n前5条分时数据:")
    for i, line in enumerate(lines[:5], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            pct = calculate_pct(close_price, prev_close)
            print(f"{i}. {time}")
            print(f"   开盘: {open_price} ({calculate_pct(open_price, prev_close)}%)")
            print(f"   收盘: {close_price} ({pct}%)")

def verify_sector_with_date(sector_name, file_pattern):
    """验证板块分时数据（带日期验证）"""
    print(f"\n=== {sector_name}板块分时数据pct计算（带日期验证）===")

    # 获取最新的板块分时文件
    latest_file = get_latest_file(file_pattern)
    if not latest_file:
        print(f"❌ 未找到{sector_name}板块分时文件")
        return

    print(f"使用分时文件: {latest_file}")

    # 提取日期
    date_str = latest_file.split('-')[2].split('.')[0]
    if date_str.isdigit() and len(date_str) == 8:
        file_date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
    else:
        file_date = "未知"
    current_date = datetime.now().strftime('%Y-%m-%d')

    print(f"分时数据日期: {file_date}")
    print(f"当前日期: {current_date}")

    # 获取昨天的收盘价（从昨天文件）
    prev_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    yesterday_file = f'data/minute/minute-{prev_date}-{file_pattern}.jsonl'

    prev_close = None
    if os.path.exists(yesterday_file):
        with open(yesterday_file, 'r') as f:
            last_line = f.readlines()[-1].strip()
            if last_line:
                parts = last_line.strip('[]\n').split(',')
                if len(parts) >= 3:
                    prev_close = float(parts[2].strip('"\' ]'))
        print(f"从昨日文件获取昨收: {prev_close}")
    else:
        print("❌ 未找到昨日文件，无法获取昨收价")

    # 读取今日分时数据
    with open(f'data/minute/{latest_file}', 'r') as f:
        lines = f.readlines()

    print(f"\n分时数据条数: {len(lines)}")
    print("\n前5条分时数据:")
    for i, line in enumerate(lines[:5], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            pct = calculate_pct(close_price, prev_close) if prev_close else None
            print(f"{i}. {time}")
            print(f"   开盘: {open_price}")
            print(f"   收盘: {close_price} ({pct}%)")

def verify_bond_etf_with_date():
    """验证国债ETF（带日期验证）"""
    print("\n=== 国债ETF分时数据pct计算（带日期验证）===")

    bond_etfs = {
        '511260': '十年国债ETF',
        '511130': '三十年国债ETF'
    }

    current_date = datetime.now().strftime('%Y-%m-%d')

    for code, name in bond_etfs.items():
        print(f"\n--- {name} ({code}) ---")

        # 检查分时数据
        minute_file = f'data/minute_data/minute_{code}_{current_date}.jsonl'
        if os.path.exists(minute_file):
            print("✅ 有分时数据")
            with open(minute_file, 'r') as f:
                lines = f.readlines()
                print(f"分时数据条数: {len(lines)}")
        else:
            print("❌ 无分时数据")

        # 获取日线数据
        daily_file = f'data/etf_daily/etf_{code}.jsonl'
        if os.path.exists(daily_file):
            with open(daily_file, 'r') as f:
                daily_lines = f.readlines()

            if len(daily_lines) >= 2:
                yesterday = json.loads(daily_lines[-2])
                today = json.loads(daily_lines[-1])

                print(f"昨日: {yesterday['date']} 收盘: {yesterday['close']}")
                print(f"今日: {today['date']} 收盘: {today['close']}")

                # 计算日线涨跌幅
                pct = calculate_pct(today['close'], yesterday['close'])
                print(f"日线涨跌幅: {pct}%")

if __name__ == "__main__":
    print("开始带日期验证的分时数据pct计算...\n")

    verify_large_cap_with_date()
    verify_sector_with_date('银行', 'bank')
    verify_sector_with_date('证券', 'broker')
    verify_bond_etf_with_date()

    print("\n验证完成！")