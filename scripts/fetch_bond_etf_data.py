#!/usr/bin/env python3
"""
补充国债ETF日线数据
511260（十年国债ETF）
511130（三十年国债ETF）
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_sector_data import _fetch_akshare_sina_etf, _save_etf_to_disk

def fetch_bond_etf_data():
    """获取国债ETF数据"""
    bond_etfs = ['sh511260', 'sh511130']

    for etf_code in bond_etfs:
        print(f"\n=== 获取 {etf_code} 数据 ===")

        try:
            # 请求365天数据
            result = _fetch_akshare_sina_etf(etf_code, limit=365)

            if result.get('data'):
                data_list = result['data']
                print(f"✅ 获取到 {len(data_list)} 条数据")
                print(f"日期范围: {data_list[0]['date']} 至 {data_list[-1]['date']}")

                # 保存到文件
                _save_etf_to_disk(etf_code, data_list)
                print(f"✅ 已保存到 data/etf_daily/etf_{etf_code.replace('sh', '')}.jsonl")

                # 显示最新数据
                latest = data_list[-1]
                print(f"最新数据: {latest}")
            else:
                print(f"❌ {etf_code} 接口返回空数据")

        except Exception as e:
            print(f"❌ {etf_code} 获取失败: {str(e)}")

if __name__ == "__main__":
    fetch_bond_etf_data()