#!/usr/bin/env python3
"""
从 archive 数据中恢复指数成交额

archive 数据格式（数组）：
- 索引25: volume（成交额，单位：万元）
- 可以用来补全 index_daily 中缺失的数据
"""

import json
from pathlib import Path
from datetime import datetime, timedelta


def extract_volume_from_archive(date_str):
    """从 archive 文件中提取成交额（万元）"""
    archive_file = f"data/archive-{date_str.replace('-', '')}.jsonl"

    if not Path(archive_file).exists():
        return None

    try:
        with open(archive_file, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line.strip())
                if isinstance(data, list) and len(data) >= 26:
                    volume_wan = data[25]  # 索引25是成交额（万元）
                    if volume_wan and volume_wan > 0:
                        return volume_wan * 10000  # 转换成元
    except:
        pass

    return None


def get_missing_dates():
    """获取需要补全的日期列表"""
    missing_dates = []

    # 从 3月31日到4月13日
    start_date = datetime(2026, 3, 31)
    end_date = datetime(2026, 4, 13)

    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        # 跳过周末
        if current.weekday() < 5:
            missing_dates.append(date_str)
        current += timedelta(days=1)

    return missing_dates


def backfill_index_from_archive(index_file, index_name):
    """从 archive 补全指数成交额"""
    if not Path(index_file).exists():
        return

    # 读取现有数据
    data = []
    with open(index_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line.strip())
                data.append(item)
            except:
                pass

    # 获取现有日期
    existing_dates = set(item['date'] for item in data)

    # 找出需要补全的日期
    missing_dates = get_missing_dates()
    new_dates = [d for d in missing_dates if d not in existing_dates]

    if not new_dates:
        print(f"  ✅ {index_name}: 数据完整")
        return 0

    print(f"  📊 {index_name}: 需要补全 {len(new_dates)} 天")

    # 从 archive 提取成交额
    filled = 0
    for date_str in new_dates:
        volume = extract_volume_from_archive(date_str)

        if volume:
            # 创建新记录
            # 从前后数据推算其他字段
            nearby = [d for d in data if d['date'] < date_str]
            if nearby:
                prev = nearby[-1]
                new_item = {
                    "date": date_str,
                    "open": prev.get("close"),
                    "high": prev.get("close"),
                    "low": prev.get("close"),
                    "close": prev.get("close"),
                    "pct": 0,
                    "amount": volume,
                    "volume": 0,
                    "turnover": None
                }
                data.append(new_item)
                filled += 1
                print(f"     ✅ {date_str}: {volume / 100000000:.2f}亿元")
        else:
            print(f"     ❌ {date_str}: 无数据")

    if filled > 0:
        # 排序并保存
        data.sort(key=lambda x: x.get('date', ''))
        with open(index_file, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')

        print(f"  ✅ {index_name}: 补全了 {filled} 天数据")

    return filled


def main():
    """主函数"""
    print("=" * 60)
    print("从 archive 数据补全指数成交额")
    print("=" * 60)

    index_files = [
        ('data/index_daily/index_000001.jsonl', '上证指数'),
        ('data/index_daily/index_399001.jsonl', '深证成指'),
    ]

    total_filled = 0
    for file_path, index_name in index_files:
        filled = backfill_index_from_archive(file_path, index_name)
        total_filled += filled

    print("\n" + "=" * 60)
    print(f"✅ 总共补全了 {total_filled} 天数据")
    print("=" * 60)


if __name__ == "__main__":
    main()
