#!/usr/bin/env python3
"""
测试ETF proxy数据获取流程
验证所有ETF是否都使用AkShare Sina接口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_sector_data import _proxy_history_payload, _load_proxy_mapping

# 检查当前proxy配置
cfg = _load_proxy_mapping()
print("=" * 80)
print("当前Proxy配置")
print("=" * 80)
print(f"默认variant: {cfg.get('default_variant')}")
print(f"强制ETF: {cfg.get('force_etf')}")
print(f"\nETF Variant映射:")
etf_map = (cfg.get('variants') or {}).get('etf') or {}
for sector, code in etf_map.items():
    print(f"  {sector}: {code}")

print("\n" + "=" * 80)
print("测试Proxy历史数据获取(使用ETF variant)")
print("=" * 80)

# 测试所有ETF sector
sectors = list(etf_map.keys())
result = _proxy_history_payload(sectors, days=365, variant="etf")

print(f"\n获取结果:")
print(f"  Variant: {result.get('variant')}")
print(f"  日期: {result.get('day')}")
print(f"  成功获取 {len([s for s in sectors if s in result.get('history', {})])}/{len(sectors)} 个板块")

print(f"\n各板块数据详情:")
for sector in sectors:
    history_data = result.get('history', {}).get(sector, [])
    if history_data:
        print(f"\n{sector}:")
        print(f"  ✅ 成功获取 {len(history_data)} 条数据")
        print(f"  起始: {history_data[0]['date']}")
        print(f"  结束: {history_data[-1]['date']}")
        print(f"  最新收盘: {history_data[-1]['close']}")

        # 检查是否满足2025-05-19的要求
        if history_data[0]['date'] <= '2025-05-19':
            print(f"  ✅ 满足起始日期要求(2025-05-19)")
        else:
            print(f"  ❌ 不满足起始日期要求,从{history_data[0]['date']}开始")
    else:
        print(f"\n{sector}:")
        print(f"  ❌ 无数据")

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)
