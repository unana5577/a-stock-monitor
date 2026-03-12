#!/usr/bin/env python3
"""
ETF历史数据回补脚本
从2025-05-19回补到当前日期
"""
import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def backfill_etf_data(start_date="2025-05-19", end_date=None):
    """
    回补ETF历史数据

    Args:
        start_date: 起始日期，默认2025-05-19
        end_date: 结束日期，默认为当前日期
    """
    from fetch_sector_data import _load_proxy_mapping, _normalize_etf_code, _fetch_tencent_daily, _fetch_ashare_daily
    import json

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"开始回补ETF数据: {start_date} 至 {end_date}")

    # 加载ETF配置
    cfg = _load_proxy_mapping()
    etf_map = cfg.get("variants", {}).get("etf", {})

    if not etf_map:
        print("❌ 未找到ETF配置")
        return

    print(f"找到 {len(etf_map)} 个ETF配置")

    # 计算需要回补的天数
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    delta = (end - start).days + 1
    limit = max(180, delta)

    results = {}

    for sector_name, etf_code in etf_map.items():
        print(f"\n处理 {sector_name} ({etf_code})...")

        # 标准化ETF代码
        normalized_code = _normalize_etf_code(etf_code)
        print(f"  标准化代码: {normalized_code}")

        # 尝试从腾讯获取
        print(f"  尝试从腾讯API获取...")
        tencent_result = _fetch_tencent_daily(normalized_code, limit=limit)

        if tencent_result.get("data") and len(tencent_result["data"]) > 0:
            data = tencent_result["data"]
            print(f"  ✅ 腾讯API获取成功: {len(data)}天")
            print(f"     起始: {data[0]['date']}")
            print(f"     结束: {data[-1]['date']}")
        else:
            # 尝试Ashare
            print(f"  ⚠️ 腾讯API无数据，尝试Ashare...")
            ashare_result = _fetch_ashare_daily(etf_code, limit=limit)

            if ashare_result.get("data") and len(ashare_result["data"]) > 0:
                data = ashare_result["data"]
                print(f"  ✅ Ashare获取成功: {len(data)}天")
            else:
                print(f"  ❌ 所有数据源均无数据")
                continue

        # 保存数据
        results[sector_name] = {
            "code": etf_code,
            "normalized_code": normalized_code,
            "data": data,
            "start_date": data[0]["date"] if data else None,
            "end_date": data[-1]["date"] if data else None,
            "count": len(data)
        }

    # 保存到文件
    output_dir = os.path.join("data", "etf_daily")
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, f"etf_backfill_{end_date}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 数据已保存到: {output_file}")

    # 生成报告
    print("\n" + "="*80)
    print("数据回补报告")
    print("="*80)
    for sector, info in results.items():
        print(f"\n{sector} ({info['code']}):")
        print(f"  数据范围: {info['start_date']} 至 {info['end_date']}")
        print(f"  数据条数: {info['count']}天")
        print(f"  数据来源: {'腾讯API' if info['normalized_code'].startswith(('sh', 'sz')) else 'Ashare'}")

    return results

if __name__ == "__main__":
    # 可以指定日期范围
    # python backfill_etf_daily.py 2025-05-19 2026-03-09
    if len(sys.argv) >= 3:
        start = sys.argv[1]
        end = sys.argv[2] if len(sys.argv) >= 3 else None
        backfill_etf_data(start, end)
    else:
        backfill_etf_data()
