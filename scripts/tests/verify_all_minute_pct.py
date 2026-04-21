#!/usr/bin/env python3
"""
验证所有分时数据的pct计算
"""

import json
import os
from datetime import datetime, timedelta

def calculate_pct(close_price, prev_close):
    """计算涨跌幅"""
    if prev_close and prev_close != 0:
        return round((close_price - prev_close) / prev_close * 100, 2)
    return None

def verify_large_cap_pct():
    """验证大盘分时数据pct"""
    print("=== 大盘分时数据pct验证 ===")

    # 读取国债期货数据作为示例（T是10年期国债）
    bond_file = 'data/minute/minute-20260320-t.jsonl'
    if not os.path.exists(bond_file):
        print("❌ 未找到国债期货文件")
        return

    with open(bond_file, 'r') as f:
        lines = f.readlines()

    # 假设昨收价
    prev_close = 134.50  # 这是昨天的收盘价

    print(f"昨收价: {prev_close}")
    print("\n前5条分时数据:")
    for i, line in enumerate(lines[:5], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            pct = calculate_pct(close_price, prev_close)
            print(f"{i}. {time} 开盘:{open_price} 收盘:{close_price} pct:{pct}%")

def verify_sector_pct():
    """验证板块分时数据pct"""
    print("\n=== 板块分时数据pct验证 ===")

    # 读取银行板块数据
    bank_file = 'data/minute/minute-20260320-bank.jsonl'
    if not os.path.exists(bank_file):
        print("❌ 未找到银行板块文件")
        return

    # 获取昨收（从昨天文件）
    prev_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
    prev_file = f'data/minute/minute-{prev_date}-bank.jsonl'

    prev_close = None
    if os.path.exists(prev_file):
        with open(prev_file, 'r') as f:
            last_line = f.readlines()[-1].strip()
            if last_line:
                parts = last_line.strip('[]\n').split(',')
                if len(parts) >= 3:
                    prev_close = float(parts[2].strip('"\' ]'))

    # 如果没有昨收文件，使用估计值
    if not prev_close:
        prev_close = 4168.50
        print(f"使用估计昨收价: {prev_close}")
    else:
        print(f"昨收价: {prev_close}")

    with open(bank_file, 'r') as f:
        lines = f.readlines()

    print("\n前5条分时数据:")
    for i, line in enumerate(lines[:5], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            pct = calculate_pct(close_price, prev_close)
            print(f"{i}. {time} 开盘:{open_price} 收盘:{close_price} pct:{pct}%")

def verify_etf_daily_pct():
    """验证ETF日线pct"""
    print("\n=== ETF日线pct验证 ===")

    # 读取半导体ETF日线数据
    etf_file = 'data/etf_daily/etf_512480.jsonl'
    if not os.path.exists(etf_file):
        print("❌ 未找到ETF日线文件")
        return

    with open(etf_file, 'r') as f:
        lines = f.readlines()

    if len(lines) < 2:
        print("❌ 数据不足")
        return

    yesterday = json.loads(lines[-2])
    today = json.loads(lines[-1])

    print(f"昨日 ({yesterday['date']}): {yesterday['close']}")
    print(f"今日 ({today['date']}): {today['close']}")

    pct = calculate_pct(today['close'], yesterday['close'])
    print(f"日线涨跌幅: {pct}%")

def verify_all_stocks_pct():
    """验证所有A股的pct（使用archive数据）"""
    print("\n=== 所有A股pct验证（archive数据） ===")

    archive_file = 'data/archive-20260324.jsonl'
    if not os.path.exists(archive_file):
        print("❌ 未找到archive文件")
        return

    with open(archive_file, 'r') as f:
        lines = f.readlines()[:5]  # 只看前5条

    print("\n前5条A股数据（第一列是时间戳，第2-5列是主要指数价格）:")
    for i, line in enumerate(lines, 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 6:
            timestamp = parts[0]
            sh_price = float(parts[1])  # 上证
            sz_price = float(parts[2])   # 深证

            print(f"{i}. 时间戳: {timestamp}")
            print(f"   上证: {sh_price}, 深证: {sz_price}")

if __name__ == "__main__":
    print("开始验证所有分时数据的pct计算...\n")

    verify_large_cap_pct()
    verify_sector_pct()
    verify_etf_daily_pct()
    verify_all_stocks_pct()

    print("\n验证完成！")