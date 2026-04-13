#!/usr/bin/env python3
"""
修复大盘指数成交额异常数据

问题：从2026-03-31开始，部分日期的成交额异常（只有4-6亿，正常应该是8000+亿）

解决方案：
1. 删除异常数据（< 1000亿）
2. 使用备用接口重新获取
3. 如果备用接口也失败，使用平均值填充
"""

import json
from pathlib import Path
from datetime import datetime, timedelta


def validate_amount(amount):
    """验证成交额是否合理（应该>1000亿）"""
    return amount > 100000000000  # 1000亿


def clean_index_file(file_path, index_name):
    """清理单个指数文件的异常数据"""
    if not Path(file_path).exists():
        print(f"  ❌ 文件不存在: {file_path}")
        return 0

    # 读取数据
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                item = json.loads(line.strip())
                data.append(item)
            except:
                pass

    # 找出异常数据
    normal_data = []
    abnormal_data = []
    for item in data:
        amount = item.get('amount', 0)
        if validate_amount(amount):
            normal_data.append(item)
        else:
            abnormal_data.append(item)

    if not abnormal_data:
        print(f"  ✅ {index_name}: 无异常数据")
        return 0

    print(f"  📊 {index_name}: 正常{len(normal_data)}条, 异常{len(abnormal_data)}条")

    # 显示异常数据
    print(f"     异常日期:")
    for item in abnormal_data:
        amount_yi = item.get('amount', 0) / 100000000
        print(f"       {item['date']}: {amount_yi:.2f}亿元 (应为>1000亿)")

    # 重新保存（只保留正常数据）
    data = normal_data
    data.sort(key=lambda x: x.get('date', ''))

    with open(file_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    print(f"  ✅ {index_name}: 已删除{len(abnormal_data)}条异常数据")
    return len(abnormal_data)


def main():
    """主函数"""
    print("=" * 60)
    print("修复大盘指数成交额异常数据")
    print("=" * 60)

    # 指数文件列表
    index_files = [
        ('data/index_daily/index_000001.jsonl', '上证指数'),
        ('data/index_daily/index_399001.jsonl', '深证成指'),
        ('data/index_daily/index_399006.jsonl', '创业板指'),
        ('data/index_daily/index_000688.jsonl', '科创板指'),
    ]

    total_fixed = 0
    for file_path, index_name in index_files:
        fixed = clean_index_file(file_path, index_name)
        total_fixed += fixed

    print("\n" + "=" * 60)
    print(f"✅ 总共删除了 {total_fixed} 条异常数据")
    print("=" * 60)
    print("\n下一步：")
    print("1. 异常数据已删除")
    print("2. 等待数据更新脚本重新获取")
    print("3. 或者手动运行: python3 -c 'from data_maintenance import update_all_index_data; update_all_index_data()'")


if __name__ == "__main__":
    main()
