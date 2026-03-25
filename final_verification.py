#!/usr/bin/env python3
"""
最终验证：所有分时数据的pct计算
"""

import os
import json
from datetime import datetime, timedelta

def calculate_pct(current, prev_close):
    """计算涨跌幅"""
    if prev_close and prev_close != 0:
        return round((current - prev_close) / prev_close * 100, 2)
    return None

def verify_large_cap():
    """验证大盘指数分时数据pct计算"""
    print("=== 大盘指数分时数据pct计算 ===")

    # 找到最新的上证指数文件
    files = []
    for f in os.listdir('data/minute'):
        if f.startswith('minute-') and 'sse' in f and f.endswith('.jsonl'):
            files.append(f)

    if not files:
        print("❌ 未找到上证指数分时文件")
        return

    # 找到最新的文件
    latest_file = max(files)
    file_path = os.path.join('data/minute', latest_file)
    print(f"使用文件: {latest_file}")

    # 读取数据
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # 获取前收盘价（从上证指数日线）
    index_file = 'data/index_daily/index_000001.jsonl'
    prev_close = None

    if os.path.exists(index_file):
        with open(index_file, 'r') as f:
            daily_lines = f.readlines()
            if len(daily_lines) >= 2:
                yesterday = json.loads(daily_lines[-2])
                prev_close = yesterday['close']
                print(f"前收盘价: {prev_close}")

    if not prev_close:
        prev_close = 3813.28  # 默认值
        print(f"使用默认前收盘价: {prev_close}")

    # 计算pct
    print("\n前5条分时数据:")
    for i, line in enumerate(lines[:5], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            open_pct = calculate_pct(open_price, prev_close)
            close_pct = calculate_pct(close_price, prev_close)

            print(f"{i}. {time}")
            print(f"   开盘: {open_price} ({open_pct}%)")
            print(f"   收盘: {close_price} ({close_pct}%)")

def verify_sectors():
    """验证板块分时数据pct计算"""
    print("\n=== 板块分时数据pct计算 ===")

    # 检查板块数据文件
    sector_files = ['bank.jsonl', 'broker.jsonl', 'insure.jsonl', 'csi2000.jsonl']

    for sector_file in sector_files:
        file_path = f'data/minute/minute-20260320-{sector_file}'
        if os.path.exists(file_path):
            print(f"\n--- {sector_file.replace('.jsonl', '')}板块 ---")

            # 读取数据
            with open(file_path, 'r') as f:
                lines = f.readlines()

            # 获取昨收价（从昨天文件）
            prev_date = (datetime.now() - timedelta(days=2)).strftime('%Y%m%d')
            prev_file = f'data/minute/minute-{prev_date}-{sector_file}'

            prev_close = None
            if os.path.exists(prev_file):
                with open(prev_file, 'r') as f:
                    last_line = f.readlines()[-1].strip()
                    if last_line:
                        parts = last_line.strip('[]\n').split(',')
                        if len(parts) >= 3:
                            prev_close = float(parts[2].strip('"\' ]'))

            if not prev_close:
                # 使用估计值
                estimates = {'bank': 4168.50, 'broker': 3890.20, 'insure': 4256.80, 'csi2000': 5023.40}
                prev_close = estimates.get(sector_file.replace('.jsonl', ''), 4000)
                print(f"使用估计前收盘价: {prev_close}")

            # 显示前3条数据
            for i, line in enumerate(lines[:3], 1):
                parts = line.strip('[]\n').split(',')
                if len(parts) >= 3:
                    time = parts[0].strip('"\' ')
                    open_price = float(parts[1].strip('"\' '))
                    close_price = float(parts[2].strip('"\' ]'))

                    pct = calculate_pct(close_price, prev_close)
                    print(f"{i}. {time} 收盘: {close_price} ({pct}%)")

def verify_bond_etf():
    """验证国债ETF分时数据"""
    print("\n=== 国债ETF分时数据pct计算 ===")

    # 国债ETF映射
    bond_etfs = {
        '511260': '十年国债ETF',
        '511130': '三十年国债ETF'
    }

    for code, name in bond_etfs.items():
        print(f"\n--- {name} ({code}) ---")

        # 检查是否存在分时数据文件
        minute_data_dir = 'data/minute_data'
        if os.path.exists(minute_data_dir):
            files = os.listdir(minute_data_dir)
            etf_file = f"minute_{code}_2026-03-24.jsonl"

            if etf_file in files:
                file_path = os.path.join(minute_data_dir, etf_file)
                with open(file_path, 'r') as f:
                    lines = f.readlines()

                print(f"找到分时数据文件: {etf_file}")
                print(f"数据条数: {len(lines)}")

                # 显示前3条
                for i, line in enumerate(lines[:3], 1):
                    data = json.loads(line.strip())
                    print(f"{i}. {data['time']} 价格: {data['price']} 成交量: {data.get('volume', 0)}")
            else:
                print(f"❌ 未找到分时数据文件: {etf_file}")

        # 检查日线数据（用于获取昨收）
        etf_daily_file = f'data/etf_daily/etf_{code}.jsonl'
        if os.path.exists(etf_daily_file):
            with open(etf_daily_file, 'r') as f:
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
    print("开始最终验证所有分时数据的pct计算...\n")

    verify_large_cap()
    verify_sectors()
    verify_bond_etf()

    print("\n验证完成！")