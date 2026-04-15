#!/usr/bin/env python3
"""
补全大盘指数成交额缺失数据（3/31-4/13）

问题：
- 腾讯接口的成交额数据单位异常（需要×1000）
- 缺失3/31-4/13的数据

解决方案：
1. 使用腾讯接口获取数据
2. 修正单位（×1000）
3. 验证数据合理性（>1000亿）
"""

import sys
sys.path.insert(0, '.')

from data_maintenance import update_index_data, get_latest_date
from datetime import datetime
import json
from pathlib import Path


def backfill_with_unit_fix(index_code, index_name):
    """补全单个指数数据，包含单位修正"""
    print(f"\n=== 处理 {index_name} ({index_code}) ===")

    try:
        from fetch_sector_data import get_index_history

        # 获取最近180天数据
        file_path = f"data/index_daily/index_{index_code}.jsonl"
        latest_date = get_latest_date(file_path)

        print(f"当前最新数据: {latest_date}")

        # 使用腾讯接口获取数据
        import akshare as ak
        df = ak.stock_zh_index_daily_tx(symbol=f"sh{index_code}" if index_code.startswith('00') else f"sz{index_code}")

        if df.empty:
            print(f"❌ 接口返回空数据")
            return 0

        # 过滤出缺失的数据
        df = df.sort_values('date')
        new_data = []

        for _, row in df.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')

            # 只补全缺失的日期
            if latest_date and date_str <= latest_date:
                continue

            # 修正成交额单位（腾讯接口需要×1000）
            amount = row['amount'] * 1000  # 单位修正

            # 验证数据合理性
            if amount < 100000000000:  # < 1000亿
                print(f"  ⚠️  {date_str}: 成交额异常 {amount/100000000:.2f}亿，跳过")
                continue

            new_item = {
                "date": date_str,
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "pct": 0,
                "amount": amount,
                "volume": 0,
                "turnover": None
            }
            new_data.append(new_item)
            print(f"  ✅ {date_str}: {amount/100000000:.2f}亿元")

        # 保存到文件
        if new_data:
            with open(file_path, 'a', encoding='utf-8') as f:
                for item in new_data:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')

            print(f"✅ {index_name}: 补全了 {len(new_data)} 天数据")
            return len(new_data)
        else:
            print(f"ℹ️  {index_name}: 无新数据需要补全")
            return 0

    except Exception as e:
        print(f"❌ {index_name}: 处理失败 - {e}")
        return 0


def main():
    """主函数"""
    print("=" * 60)
    print("补全大盘指数成交额数据（3/31-4/13）")
    print("=" * 60)

    index_list = [
        ('000001', '上证指数'),
        ('399001', '深证成指'),
        ('399006', '创业板指'),
        ('000688', '科创板指'),
    ]

    total_filled = 0
    for code, name in index_list:
        filled = backfill_with_unit_fix(code, name)
        total_filled += filled

    print("\n" + "=" * 60)
    print(f"✅ 总共补全了 {total_filled} 条数据")
    print("=" * 60)


if __name__ == "__main__":
    main()
