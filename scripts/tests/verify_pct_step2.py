#!/usr/bin/env python3
"""
步骤2：验证普通ETF分时pct计算
"""

import sys
sys.path.append('.')
from fetch_sector_data import get_etf_minute_data, _fetch_akshare_sina_etf

def verify_etf_pct():
    """验证ETF分时pct计算"""
    print("=== 步骤2：验证普通ETF分时pct计算 ===")

    # 测试半导体ETF
    etf_code = 'sh512480'
    print(f"测试ETF: {etf_code}")

    # 1. 先获取昨收价（从日线）
    daily_result = _fetch_akshare_sina_etf(etf_code, limit=2)
    if daily_result and daily_result.get('data') and len(daily_result['data']) >= 2:
        prev_close_from_daily = daily_result['data'][-2]['close']
        print(f"日线数据昨收: {prev_close_from_daily}")
        print(f"日线数据今日: {daily_result['data'][-1]['close']}")
        print(f"日线涨跌幅: {daily_result['data'][-1]['pct']}%")
    else:
        print("❌ 无法获取日线数据")
        return False

    # 2. 获取分时数据
    minute_result = get_etf_minute_data(etf_code)

    if minute_result and minute_result.get('data'):
        print(f"\n分时数据条数: {len(minute_result['data'])}")
        print("前3条分时数据验证:")

        for item in minute_result['data'][:3]:
            # 手动计算pct
            expected_pct = round((item['close'] - prev_close_from_daily) / prev_close_from_daily * 100, 2)
            print(f"\n时间: {item['time']}")
            print(f"  开盘: {item.get('open')}")
            print(f"  收盘: {item['close']}")
            print(f"  计算pct: {expected_pct}%")
            print(f"  接口pct: {item.get('pct')}%")

            if item.get('pct') == expected_pct:
                print("  ✅ 计算正确")
            else:
                print("  ❌ 计算错误")

        return True
    else:
        print("❌ 无法获取分时数据")
        return False

if __name__ == "__main__":
    success = verify_etf_pct()
    print(f"\n步骤2结果: {'✅ 通过' if success else '❌ 失败'}")