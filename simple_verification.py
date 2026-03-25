#!/usr/bin/env python3
"""
简单验证：使用正确的日期逻辑
"""

import os
import json
from datetime import datetime, timedelta

def extract_date_from_filename(filename):
    """从文件名提取日期"""
    # 文件名格式: minute-YYYYMMDD-sse.jsonl
    parts = filename.split('-')
    if len(parts) >= 3:
        date_str = parts[1]  # YYYYMMDD
        if date_str.isdigit() and len(date_str) == 8:
            return datetime.strptime(date_str, '%Y%m%d')
    return None

def get_latest_daily_close(code):
    """获取日线最新收盘价"""
    file_path = f'data/index_daily/index_{code}.jsonl'
    if not os.path.exists(file_path):
        return None

    with open(file_path, 'r') as f:
        lines = f.readlines()

    if not lines:
        return None

    # 获取最后一条数据
    latest = json.loads(lines[-1])
    return latest['close']

def calculate_pct(current, prev_close):
    """计算涨跌幅"""
    if prev_close and prev_close != 0:
        return round((current - prev_close) / prev_close * 100, 2)
    return None

def verify_correct_calculation():
    """验证正确的计算逻辑"""
    print("=== 正确的分时数据pct计算 ===\n")

    # 1. 大盘指数（使用日线昨收）
    print("1. 大盘指数（上证）")
    latest_daily_close = get_latest_daily_close('000001')
    print(f"   日线昨收: {latest_daily_close}")

    # 读取最新分时文件
    files = []
    for f in os.listdir('data/minute'):
        if 'sse' in f and f.endswith('.jsonl'):
            files.append(f)

    if files:
        latest_file = max(files)
        file_date = extract_date_from_filename(latest_file)

        print(f"   分时文件: {latest_file} ({file_date.strftime('%Y-%m-%d')})")

        # 获取前一日收盘价（用于计算pct）
        prev_day_close = latest_daily_close

        with open(f'data/minute/{latest_file}', 'r') as f:
            lines = f.readlines()

        print(f"   数据条数: {len(lines)}")
        print("   前3条分时数据:")
        for i, line in enumerate(lines[:3], 1):
            parts = line.strip('[]\n').split(',')
            if len(parts) >= 3:
                time = parts[0].strip('"\' ')
                open_price = float(parts[1].strip('"\' '))
                close_price = float(parts[2].strip('"\' ]'))

                open_pct = calculate_pct(open_price, prev_day_close)
                close_pct = calculate_pct(close_price, prev_day_close)

                print(f"   {i}. {time}")
                print(f"      开盘: {open_price} ({open_pct}%)")
                print(f"      收盘: {close_price} ({close_pct}%)")

    print("\n" + "="*50 + "\n")

    # 2. 板块数据（需要从昨日分时文件获取）
    print("2. 板块数据（银行板块）")

    # 获取今日和昨日的文件
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    today_str = yesterday.strftime('%Y%m%d')  # 使用昨天的文件
    yesterday_str = day_before.strftime('%Y%m%d')

    bank_file_today = f'data/minute/minute-{today_str}-bank.jsonl'
    bank_file_yesterday = f'data/minute/minute-{yesterday_str}-bank.jsonl'

    print(f"   今日文件: {bank_file_today}")
    print(f"   昨日文件: {bank_file_yesterday}")

    # 从昨日文件获取昨收
    prev_close = None
    if os.path.exists(bank_file_yesterday):
        with open(bank_file_yesterday, 'r') as f:
            last_line = f.readlines()[-1].strip()
            if last_line:
                parts = last_line.strip('[]\n').split(',')
                if len(parts) >= 3:
                    prev_close = float(parts[2].strip('"\' ]'))
                    print(f"   昨收价: {prev_close}")

    if not prev_close:
        print("   ❌ 无法获取昨收价")

    # 读取今日数据
    if os.path.exists(bank_file_today):
        with open(bank_file_today, 'r') as f:
            lines = f.readlines()

        print(f"   数据条数: {len(lines)}")
        print("   前3条分时数据:")
        for i, line in enumerate(lines[:3], 1):
            parts = line.strip('[]\n').split(',')
            if len(parts) >= 3:
                time = parts[0].strip('"\' ')
                open_price = float(parts[1].strip('"\' '))
                close_price = float(parts[2].strip('"\' ]'))

                pct = calculate_pct(close_price, prev_close) if prev_close else None

                print(f"   {i}. {time}")
                print(f"      开盘: {open_price}")
                print(f"      收盘: {close_price} ({pct}%)")

    print("\n" + "="*50 + "\n")

    # 3. 国债ETF（使用日线数据）
    print("3. 国债ETF日线涨跌幅")

    bond_etfs = {
        '511260': '十年国债ETF',
        '511130': '三十年国债ETF'
    }

    for code, name in bond_etfs.items():
        print(f"\n   {name} ({code}):")

        etf_file = f'data/etf_daily/etf_{code}.jsonl'
        if os.path.exists(etf_file):
            with open(etf_file, 'r') as f:
                lines = f.readlines()

            if len(lines) >= 2:
                yesterday = json.loads(lines[-2])
                today = json.loads(lines[-1])

                print(f"   昨日: {yesterday['date']} {yesterday['close']}")
                print(f"   今日: {today['date']} {today['close']}")

                pct = calculate_pct(today['close'], yesterday['close'])
                print(f"   涨跌幅: {pct}%")

if __name__ == "__main__":
    verify_correct_calculation()