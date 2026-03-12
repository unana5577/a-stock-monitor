#!/usr/bin/env python3
"""
测试ETF数据集成
验证_fetch_akshare_sina_etf函数是否正常工作
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_sector_data import _fetch_akshare_sina_etf, _fetch_tencent_daily

# 测试ETF代码列表
test_etfs = {
    '半导体': 'sh512480',
    '新能源': 'sh516160',
    '创新药': 'sh512690',
    '有色金属': 'sh512400',
    '通讯设备': 'sh515880'
}

print("=" * 80)
print("测试AkShare Sina ETF接口集成")
print("=" * 80)

# 测试1: 直接调用_fetch_akshare_sina_etf
print("\n测试1: 直接调用_fetch_akshare_sina_etf(使用365天)\n")
for sector, code in test_etfs.items():
    print(f"{sector} ({code}):")
    result = _fetch_akshare_sina_etf(code, limit=365)

    if result.get("data"):
        data = result["data"]
        print(f"  ✅ 成功获取 {len(data)} 条数据")
        print(f"  起始: {data[0]['date']}")
        print(f"  结束: {data[-1]['date']}")
        print(f"  最新收盘: {data[-1]['close']}")

        # 检查是否满足2025-05-19的要求
        if data[0]['date'] <= '2025-05-19':
            print(f"  ✅ 满足起始日期要求(2025-05-19)")
        else:
            print(f"  ❌ 不满足起始日期要求,从{data[0]['date']}开始")
    else:
        print(f"  ❌ 无数据")
    print()

# 测试2: 通过_fetch_tencent_daily调用(会自动检测ETF并使用AkShare Sina)
print("\n" + "=" * 80)
print("测试2: 通过_fetch_tencent_daily调用(自动检测ETF)")
print("=" * 80 + "\n")

for sector, code in test_etfs.items():
    print(f"{sector} ({code}):")
    result = _fetch_tencent_daily(code, limit=365)

    if result.get("data"):
        data = result["data"]
        print(f"  ✅ 成功获取 {len(data)} 条数据")
        print(f"  起始: {data[0]['date']}")
        print(f"  结束: {data[-1]['date']}")
    else:
        print(f"  ❌ 无数��")
    print()

print("=" * 80)
print("测试完成")
print("=" * 80)
