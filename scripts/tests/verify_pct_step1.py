#!/usr/bin/env python3
"""
步骤1：验证大盘指数分时pct计算
"""

import sys
sys.path.append('.')
from fetch_sector_data import _fetch_ashare_minute

def verify_large_cap_pct():
    """验证大盘指数分时pct计算"""
    print("=== 步骤1：验证大盘指数分时pct计算 ===")

    # 测试上证指数
    result = _fetch_ashare_minute('sh000001', count=3)

    print(f"接口返回prevClose: {result.get('prevClose')}")
    print(f"数据条数: {len(result.get('data', []))}")

    if result.get('data'):
        print("\n验证计算:")
        for item in result['data'][:3]:
            # 手动计算pct
            expected_pct = round((item['close'] - result['prevClose']) / result['prevClose'] * 100, 2)
            print(f"时间: {item['time']}")
            print(f"  收盘: {item['close']}")
            print(f"  计算pct: {expected_pct}%")
            print(f"  接口pct: {item.get('pct')}%")

            if item.get('pct') == expected_pct:
                print("  ✅ 计算正确")
            else:
                print("  ❌ 计算错误")

    return result.get('data') is not None and len(result.get('data', [])) > 0

if __name__ == "__main__":
    success = verify_large_cap_pct()
    print(f"\n步骤1结果: {'✅ 通过' if success else '❌ 失败'}")