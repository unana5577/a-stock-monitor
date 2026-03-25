#!/usr/bin/env python3
"""
正确验证大盘指数分时数据
"""

import os

def verify_sh_index_pct():
    """验证上证指数分时数据"""
    print("=== 上证指数分时数据pct验证 ===")

    # 读取上证分时数据
    sse_file = 'data/minute/minute-20260313-sse.jsonl'
    if not os.path.exists(sse_file):
        print("❌ 未找到上证指数文件")
        return

    with open(sse_file, 'r') as f:
        lines = f.readlines()

    # 假设前收盘价（实际应该从日线获取）
    prev_close = 3813.28  # 这是昨天的上证收盘价

    print(f"昨收价: {prev_close}")
    print("\n前5条分时数据:")
    for i, line in enumerate(lines[:5], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            # 计算涨跌幅
            pct = round((close_price - prev_close) / prev_close * 100, 2)
            print(f"{i}. {time} 开盘:{open_price} 收盘:{close_price} pct:{pct}%")

def verify_gem_index_pct():
    """验证创业板指分时数据"""
    print("\n=== 创业板指分时数据pct验证 ===")

    # 读取创业板指分时数据
    gem_file = 'data/minute/minute-20260313-gem.jsonl'
    if not os.path.exists(gem_file):
        print("❌ 未找到创业板指文件")
        return

    with open(gem_file, 'r') as f:
        lines = f.readlines()

    # 假设前收盘价
    prev_close = 2580.50

    print(f"昨收价: {prev_close}")
    print("\n前5条分时数据:")
    for i, line in enumerate(lines[:5], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            pct = round((close_price - prev_close) / prev_close * 100, 2)
            print(f"{i}. {time} 开盘:{open_price} 收盘:{close_price} pct:{pct}%")

def verify_bond_futures_pct():
    """验证国债期货分时数据"""
    print("\n=== 国债期货分时数据pct验证 ===")

    # 读取10年期国债期货分时数据
    bond_file = 'data/minute/minute-20260313-t.jsonl'
    if not os.path.exists(bond_file):
        print("❌ 未找到国债期货文件")
        return

    with open(bond_file, 'r') as f:
        lines = f.readlines()

    # 假设前收盘价
    prev_close = 134.50

    print(f"昨收价: {prev_close}")
    print("\n前5条分时数据:")
    for i, line in enumerate(lines[:5], 1):
        parts = line.strip('[]\n').split(',')
        if len(parts) >= 3:
            time = parts[0].strip('"\' ')
            open_price = float(parts[1].strip('"\' '))
            close_price = float(parts[2].strip('"\' ]'))

            pct = round((close_price - prev_close) / prev_close * 100, 2)
            print(f"{i}. {time} 开盘:{open_price} 收盘:{close_price} pct:{pct}%")

if __name__ == "__main__":
    print("开始验证正确的分时数据...\n")

    verify_sh_index_pct()
    verify_gem_index_pct()
    verify_bond_futures_pct()

    print("\n验证完成！")
    print("\n注意：")
    print("- sse.jsonl 是上证指数，不是国债期货")
    print("- t.jsonl 才是10年期国债期货")
    print("- 其他期货目前系统不支持")