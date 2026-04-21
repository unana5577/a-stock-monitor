#!/usr/bin/env python3
"""
测试板块分时数据持久化
"""

import sys
import os
import json
from datetime import datetime

sys.path.append('.')
from fetch_sector_data import get_minute_data_from_akshare

def test_sector_persistence():
    """测试板块分时数据持久化"""
    print("=== 测试板块分时数据持久化 ===\n")

    # 板块配置
    sectors = {
        '90.BK0475': 'bank',    # 银行
        '90.BK0473': 'broker',  # 证券
        '90.BK0474': 'insure',  # 保险
        '2.932000': 'csi2000'  # 中证2000
    }

    today = datetime.now().strftime('%Y%m%d')
    print(f"今天日期: {today}\n")

    for secid, code in sectors.items():
        print(f"--- 测试 {code} 板块 ({secid}) ---")

        # 调用接口获取分时数据
        result = get_minute_data_from_akshare(secid)

        if result and result.get('data'):
            data = result['data']
            print(f"✅ 接口返回数据: {len(data)} 条")
            print(f"  prevClose: {result.get('prevClose')}")

            if data:
                print(f"  第一条: {data[0]}")
                print(f"  最后一条: {data[-1]}")

            # 尝试持久化到文件
            file_path = f'data/minute/minute-{today}-{code}.jsonl'
            try:
                os.makedirs('data/minute', exist_ok=True)

                with open(file_path, 'w') as f:
                    for item in data:
                        f.write(json.dumps([item['time'], item['open'], item['close']]) + '\n')

                print(f"✅ 已持久化到: {file_path}")

                # 验证文件
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                print(f"  文件行数: {len(lines)}")

            except Exception as e:
                print(f"❌ 持久化失败: {e}")

        else:
            print(f"❌ 接口返回空数据")

        print()

if __name__ == "__main__":
    test_sector_persistence()