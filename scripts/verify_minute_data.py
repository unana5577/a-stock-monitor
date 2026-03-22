#!/usr/bin/env python3
"""
分时数据验证工具
验证：板块分时、volume、旧版文件
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path


def load_holidays():
    """加载节假日配置"""
    holidays_file = Path("config/holidays.json")
    if not holidays_file.exists():
        return set()

    with open(holidays_file, 'r', encoding='utf-8') as f:
        import json
        data = json.load(f)
        return set(data.get('holidays', []))


def is_trading_day(date, holidays):
    """判断是否为交易日"""
    date_str = date.strftime('%Y-%m-%d')
    if date.weekday() >= 5:
        return False
    if date_str in holidays:
        return False
    return True


def get_last_n_trading_days(end_date, n, holidays):
    """获取最近N个交易日"""
    dates = []
    current = end_date
    while len(dates) < n:
        if is_trading_day(current, holidays):
            dates.append(current)
        current -= timedelta(days=1)
    return dates


def verify_minute_data():
    """验证板块分时数据（data/minute/）"""
    print("\n" + "="*80)
    print("📊 板块分时数据（data/minute/）")
    print("="*80)

    minute_dir = Path("data/minute")
    if not minute_dir.exists():
        print("❌ data/minute/ 目录不存在")
        return None

    pattern = re.compile(r"minute-(\d{6})-(\w+)\.jsonl$")
    files = []

    for file in minute_dir.glob("minute-*.jsonl"):
        match = pattern.search(file.name)
        if match:
            date_str = match.group(1)
            sector = match.group(2)
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                size = file.stat().st_size
                files.append((file_date, sector, file, size))
            except ValueError:
                pass

    if not files:
        print("❌ 未找到板块分时文件")
        return None

    # 按日期分组
    dates = {}
    for file_date, sector, file, size in files:
        date_key = file_date.strftime('%Y-%m-%d')
        if date_key not in dates:
            dates[date_key] = []
        dates[date_key].append(sector)

    sorted_dates = sorted(dates.keys(), reverse=True)

    print(f"✅ 分时文件总数：{len(files)} 个")
    print(f"📅 覆盖日期数：{len(sorted_dates)} 天")
    print(f"📂 最新日期：{sorted_dates[0] if sorted_dates else 'N/A'}")
    print(f"📂 最早日期：{sorted_dates[-1] if sorted_dates else 'N/A'}")

    # 检查最近5个交易日
    holidays = load_holidays()
    today = datetime.now().date()
    target_dates = get_last_n_trading_days(datetime(today.year, today.month, today.day), 5, holidays)

    print(f"\n📋 最近5个交易日分时数据：")
    for date in target_dates:
        date_str = date.strftime('%Y-%m-%d')
        if date_str in dates:
            print(f"   ✅ {date_str}：{len(dates[date_str])} 个板块")
        else:
            print(f"   ❌ {date_str}：缺失")

    return {
        'total_files': len(files),
        'dates_count': len(sorted_dates),
        'latest': sorted_dates[0] if sorted_dates else None,
        'earliest': sorted_dates[-1] if sorted_dates else None
    }


def verify_volume_data():
    """验证成交额分时数据（volume）"""
    print("\n" + "="*80)
    print("📊 成交额分时数据（volume）")
    print("="*80)

    data_dir = Path("data")
    pattern = re.compile(r"volume-(\d{8})\.jsonl$")
    files = []

    for file in data_dir.glob("volume-*.jsonl"):
        match = pattern.search(file.name)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                size = file.stat().st_size
                files.append((file_date, file, size))
            except ValueError:
                pass

    files.sort(key=lambda x: x[0])

    if not files:
        print("❌ 未找到 volume 文件")
        return None

    earliest = files[0][0]
    latest = files[-1][0]

    print(f"✅ 文件数量：{len(files)} 个")
    print(f"📅 日期范围：{earliest.strftime('%Y-%m-%d')} 至 {latest.strftime('%Y-%m-%d')}")

    return {
        'count': len(files),
        'earliest': earliest,
        'latest': latest
    }


def verify_old_minute_files():
    """验证根目录旧版分时文件"""
    print("\n" + "="*80)
    print("📊 根目录旧版分时文件（待清理）")
    print("="*80)

    data_dir = Path("data")
    pattern = re.compile(r"minute-(\d{8})-(\w+)\.jsonl$")
    files = []

    for file in data_dir.glob("minute-*.jsonl"):
        match = pattern.search(file.name)
        if match:
            date_str = match.group(1)
            sector = match.group(2)
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                size = file.stat().st_size
                files.append((file_date, sector, file, size))
            except ValueError:
                pass

    if not files:
        print("✅ 未找到旧版分时文件")
        return None

    # 按日期分组
    dates = {}
    for file_date, sector, file, size in files:
        date_key = file_date.strftime('%Y-%m-%d')
        if date_key not in dates:
            dates[date_key] = []
        dates[date_key].append((sector, size))

    sorted_dates = sorted(dates.keys())

    print(f"⚠️  旧版文件总数：{len(files)} 个")
    print(f"📅 日期范围：{sorted_dates[0]} 至 {sorted_dates[-1]}")
    print(f"📋 按日期统计：")

    for date in sorted_dates:
        sectors = dates[date]
        total_size = sum(s[1] for s in sectors)
        print(f"   - {date}：{len(sectors)} 个板块, {total_size / 1024:.1f} KB")

    print(f"\n🗑️  建议清理：Task #13")

    return {
        'total_files': len(files),
        'dates': sorted_dates,
        'size_total': sum(f[3] for f in files)
    }


def main():
    """主函数"""
    print("="*80)
    print("🔍 分时数据验证工具".center(80))
    print("="*80)
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 验证各类分时数据
    minute_result = verify_minute_data()
    volume_result = verify_volume_data()
    old_result = verify_old_minute_files()

    # 汇总报告
    print("\n" + "="*80)
    print("📋 验证汇总")
    print("="*80)

    print(f"\n✅ 验证完成：")
    print(f"   - 板块分时：{'通过' if minute_result else '失败'}")
    print(f"   - 成交额分时：{'通过' if volume_result else '失败'}")
    print(f"   - 旧版文件：{'发现' if old_result else '无'}")

    if old_result:
        print(f"\n🗑️  清理任务：")
        print(f"   - #13：清理根目录旧版分时文件（{old_result['total_files']} 个）")

    print("\n" + "="*80)


if __name__ == "__main__":
    main()
