#!/usr/bin/env python3
"""
验证修改后的分时数据接口
"""

import sys
sys.path.append('.')
from fetch_sector_data import _fetch_ashare_minute, get_etf_minute_data, get_minute_data_from_akshare

def test_large_cap():
    """测试大盘指数分时"""
    print("=== 测试大盘指数分时（上证） ===")
    result = _fetch_ashare_minute('sh000001', count=5)
    print(f"数据条数: {len(result.get('data', []))}")
    print(f"prevClose: {result.get('prevClose')}")
    if result.get('data'):
        print("前3条数据:")
        for item in result['data'][:3]:
            print(f"  {item}")

def test_etf():
    """测试ETF分时"""
    print("\n=== 测试ETF分时（半导体ETF） ===")
    result = get_etf_minute_data('sh512480')
    if result:
        print(f"数据条数: {len(result.get('data', []))}")
        print(f"prevClose: {result.get('prevClose')}")
        if result.get('data'):
            print("前3条数据:")
            for item in result['data'][:3]:
                print(f"  {item}")
    else:
        print("❌ 无数据")

def test_sector():
    """测试板块分时"""
    print("\n=== 测试板块分时（银行） ===")
    result = get_minute_data_from_akshare('90.BK0475')
    if result:
        print(f"数据条数: {len(result.get('data', []))}")
        print(f"prevClose: {result.get('prevClose')}")
        if result.get('data'):
            print("前3条数据:")
            for item in result['data'][:3]:
                print(f"  {item}")
    else:
        print("❌ 无数据")

if __name__ == "__main__":
    test_large_cap()
    test_etf()
    test_sector()