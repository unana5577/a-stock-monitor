#!/usr/bin/env python3
"""
分时数据涨跌幅计算测试脚本
测试大盘、板块、ETF三种数据类型的pct计算
"""

import json
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fetch_sector_data import (
    _fetch_ashare_minute,
    get_minute_data_from_akshare,
    get_etf_minute_data,
    _fetch_tencent_daily
)

def test_large_cap_pct():
    """测试大盘分时数据pct计算（上证指数）"""
    print("=== 测试大盘分时数据（上证指数）===")
    try:
        result = _fetch_ashare_minute("sh000001", count=5)
        if not result or not result.get("data"):
            print("❌ 无数据")
            return

        data = result["data"]
        prev_close = result.get("prevClose")
        print(f"前收盘价: {prev_close}")
        print("\n分时数据:")
        for item in data[:3]:
            pct = None
            if prev_close and prev_close != 0:
                pct = round((item['close'] - prev_close) / prev_close * 100, 2)
            print(f"时间: {item['time']}, 开盘: {item['open']}, 收盘: {item['close']}, pct: {pct}%")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")

def test_sector_pct():
    """测试板块分时数据pct计算（银行板块）"""
    print("\n=== 测试板块分时数据（银行板块）===")
    try:
        # 东财银行板块代码: 90.BK0475
        result = get_minute_data_from_akshare("90.BK0475")
        if not result or not result.get("data"):
            print("❌ 无数据")
            return

        data = result["data"]
        print(f"数据条数: {len(data)}")
        print("\n分时数据:")
        for item in data[:3]:
            print(f"时间: {item['time']}, 价格: {item['price']}, 成交量: {item.get('volume', 0)}")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")

def test_etf_pct():
    """测试ETF分时数据pct计算（半导体ETF）"""
    print("\n=== 测试ETF分时数据（半导体ETF）===")
    try:
        result = get_etf_minute_data("sh512480")
        if not result or not result.get("data"):
            print("❌ 无数据")
            return

        data = result["data"]
        print(f"数据条数: {len(data)}")
        print("\n分时数据:")
        for item in data[:3]:
            print(f"时间: {item['time']}, 价格: {item['price']}, 成交量: {item.get('volume', 0)}")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")

def test_etf_daily_prev_close():
    """测试ETF日线数据获取昨收价"""
    print("\n=== 测试ETF日线昨收价（用于ETF分时pct计算）===")
    try:
        result = _fetch_tencent_daily("sh512480", limit=2)
        if result and result.get("data"):
            daily_data = result["data"]
            if len(daily_data) >= 2:
                yesterday = daily_data[-2]
                today = daily_data[-1]
                print(f"昨日: {yesterday['date']}, 收盘: {yesterday['close']}")
                print(f"今日: {today['date']}, 收盘: {today['close']}")

                # 计算今日涨跌幅
                if yesterday['close'] != 0:
                    daily_pct = round((today['close'] - yesterday['close']) / yesterday['close'] * 100, 2)
                    print(f"日线涨跌幅: {daily_pct}%")
            else:
                print("❌ 数据不足2天")
        else:
            print("❌ 无数据")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")

if __name__ == "__main__":
    print("开始测试分时数据涨跌幅计算...\n")

    # 测试各类分时数据
    test_large_cap_pct()
    test_sector_pct()
    test_etf_pct()
    test_etf_daily_prev_close()

    print("\n测试完成！")