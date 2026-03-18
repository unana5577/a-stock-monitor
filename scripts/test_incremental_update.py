#!/usr/bin/env python3
"""
测试ETF增量更新功能
补全缺失0316数据的ETF
"""
import sys
import os
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_incremental_update():
    """测试增量更新"""
    from fetch_sector_data import _update_etf_incremental

    # 需要补全的ETF（缺失0316数据）
    missing_etfs = {
        "sh512480": "半导体",
        "sh516160": "新能源",
        "sh512400": "有色金属",
        "sh515880": "通讯设备"
    }

    print("=" * 80)
    print("ETF增量更新测试")
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = {}

    for etf_code, etf_name in missing_etfs.items():
        print(f"\n{'─' * 80}")
        print(f"处理 {etf_name} ({etf_code})...")
        print(f"{'─' * 80}")

        try:
            # 执行增量更新
            data = _update_etf_incremental(etf_code, required_days=60)

            if data:
                latest_date = data[-1]['date']
                print(f"\n✅ {etf_name} 更新成功")
                print(f"   获取数据条数: {len(data)}")
                print(f"   最新交易日期: {latest_date}")

                results[etf_code] = {
                    "name": etf_name,
                    "success": True,
                    "count": len(data),
                    "latest_date": latest_date
                }
            else:
                print(f"\n❌ {etf_name} 更新失败：未获取到数据")
                results[etf_code] = {
                    "name": etf_name,
                    "success": False,
                    "error": "未获取到数据"
                }
        except Exception as e:
            print(f"\n❌ {etf_name} 更新异常: {str(e)}")
            results[etf_code] = {
                "name": etf_name,
                "success": False,
                "error": str(e)
            }

    # 输出汇总报告
    print("\n" + "=" * 80)
    print("更新汇总报告")
    print("=" * 80)

    success_count = sum(1 for r in results.values() if r.get('success'))
    total_count = len(results)

    print(f"\n总计: {success_count}/{total_count} 个ETF更新成功\n")

    for etf_code, info in results.items():
        status = "✅" if info.get('success') else "❌"
        print(f"{status} {info['name']} ({etf_code})")
        if info.get('success'):
            print(f"   最新日期: {info['latest_date']}")
        else:
            print(f"   错误: {info.get('error', 'Unknown')}")

    # 检查是否所有ETF都更新到0316
    print("\n" + "=" * 80)
    print("验证结果")
    print("=" * 80)

    all_updated = all(
        r.get('success') and r.get('latest_date') == '2026-03-16'
        for r in results.values()
    )

    if all_updated:
        print("\n🎉 所有ETF已成功更新到 2026-03-16")
    else:
        print("\n⚠️ 部分ETF未更新到最新日期，请检查日志")

    return results

if __name__ == "__main__":
    test_incremental_update()
