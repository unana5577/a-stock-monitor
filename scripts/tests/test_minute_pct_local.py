#!/usr/bin/env python3
"""
分时数据涨跌幅计算测试脚本（使用本地数据）
"""

import json
import os
from datetime import datetime, timedelta

def test_large_cap_pct_local():
    """测试大盘分时数据pct计算（使用本地文件）"""
    print("=== 测试大盘分时数据（本地文件）===")

    # 查找最新的分时文件
    minute_files = []
    for file in os.listdir('data/minute'):
        if file.startswith('minute-') and file.endswith('.jsonl'):
            minute_files.append(file)

    if not minute_files:
        print("❌ 未找到分时数据文件")
        return

    # 找到最新的上证文件
    sse_file = None
    for file in minute_files:
        if 'sse' in file:
            sse_file = file
            break

    if not sse_file:
        print("❌ 未找到上证分时文件")
        return

    file_path = os.path.join('data/minute', sse_file)
    print(f"使用文件: {file_path}")

    # 读取分时数据
    with open(file_path, 'r') as f:
        lines = f.readlines()

    if len(lines) < 2:
        print("❌ 数据不足")
        return

    # 解析最后3行数据
    print("\n最后3条分时数据:")
    for i, line in enumerate(lines[-3:], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            # 模拟前收盘价（这里假设前收盘是3813.28）
            prev_close = 3813.28
            pct = round((close_price - prev_close) / prev_close * 100, 2)

            print(f"第{i}: 时间: {time}, 开盘: {open_price}, 收盘: {close_price}, pct: {pct}%")

def test_sector_pct_local():
    """测试板块分时数据pct计算（使用本地文件）"""
    print("\n=== 测试板块分时数据（本地文件）===")

    # 查找银行板块文件
    bank_file = 'data/minute/minute-20260320-bank.jsonl'
    if not os.path.exists(bank_file):
        print("❌ 未找到银行板块分时文件")
        return

    print(f"使用文件: {bank_file}")

    # 读取分时数据
    with open(bank_file, 'r') as f:
        lines = f.readlines()

    if len(lines) < 2:
        print("❌ 数据不足")
        return

    # 获取昨收价（从上个交易日的分时文件）
    prev_date = (datetime.now() - timedelta(days=2)).strftime('%Y%m%d')
    prev_file = f'data/minute/minute-{prev_date}-bank.jsonl'

    prev_close = None
    if os.path.exists(prev_file):
        with open(prev_file, 'r') as f:
            last_line = f.readlines()[-1].strip()
            if last_line:
                parts = last_line.split(',')
                if len(parts) >= 3:
                    prev_close = float(parts[2])

    if not prev_close:
        # 使用一个估计值
        prev_close = 4168.50

    print(f"昨日收盘价: {prev_close}")

    # 解析最后3行数据
    print("\n最后3条分时数据:")
    for i, line in enumerate(lines[-3:], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            pct = round((close_price - prev_close) / prev_close * 100, 2)

            print(f"第{i}: 时间: {time}, 开盘: {open_price}, 收盘: {close_price}, pct: {pct}%")

def test_etf_daily_pct():
    """测试ETF日线涨跌幅（用于验证计算逻辑）"""
    print("\n=== 测试ETF日线涨跌幅（本地文件）===")

    etf_file = 'data/etf_daily/etf_512480.jsonl'
    if not os.path.exists(etf_file):
        print("❌ 未找到ETF日线文件")
        return

    print(f"使用文件: {etf_file}")

    # 读取最后2条日线数据
    with open(etf_file, 'r') as f:
        lines = f.readlines()

    if len(lines) < 2:
        print("❌ 数据不足")
        return

    yesterday_data = json.loads(lines[-2])
    today_data = json.loads(lines[-1])

    print(f"昨日: {yesterday_data['date']}, 收盘: {yesterday_data['close']}")
    print(f"今日: {today_data['date']}, 收盘: {today_data['close']}")

    # 计算日线涨跌幅
    pct = round((today_data['close'] - yesterday_data['close']) / yesterday_data['close'] * 100, 2)
    print(f"日线涨跌幅: {pct}%")

if __name__ == "__main__":
    print("开始测试分时数据涨跌幅计算（使用本地数据）...\n")

    test_large_cap_pct_local()
    test_sector_pct_local()
    test_etf_daily_pct()

    print("\n测试完成！")