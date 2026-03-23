#!/usr/bin/env python3
"""
warmup数据验证工具 - 时间感知版本
运行时间: 15:30
检查内容: warmup文件存在性、60天数据完整性
"""

import sys
import re
import json
from datetime import datetime, timedelta
from pathlib import Path


def load_holidays():
    """加载节假日配置"""
    holidays_file = Path("config/holidays.json")
    if not holidays_file.exists():
        return set()

    with open(holidays_file, 'r', encoding='utf-8') as f:
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


def log_output(message):
    """输出到stdout和日志"""
    print(message)


def verify_archive_files():
    """验证archive文件（60天数据完整性）"""
    log_output("\n📊 大盘综合归档数据（archive）")

    data_dir = Path("data")
    pattern = re.compile(r"archive-(\d{8})\.jsonl$")
    files = []

    for file in data_dir.glob("archive-*.jsonl"):
        match = pattern.search(file.name)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                files.append(file_date)
            except ValueError:
                pass

    if not files:
        log_output("   ❌ 未找到 archive 文件")
        return False

    # 检查最近60天完整性
    holidays = load_holidays()
    today = datetime.now()
    target_dates = get_last_n_trading_days(today, 60, holidays)

    existing_dates = set(f.date() for f in files)
    real_missing = []

    for date in target_dates:
        if date.date() not in existing_dates:
            date_str = date.strftime('%Y-%m-%d')
            if date_str not in holidays:
                real_missing.append(date)

    total_files = len(files)
    missing_count = len(real_missing)

    log_output(f"   📁 文件数量：{total_files} 个")
    log_output(f"   📅 日期范围：{min(files).strftime('%Y-%m-%d')} 至 {max(files).strftime('%Y-%m-%d')}")

    if missing_count == 0:
        log_output(f"   ✅ 最近60交易日数据完整")
        return True
    else:
        log_output(f"   ⚠️  最近60交易日缺失：{missing_count} 天")
        if missing_count <= 10:
            for i, date in enumerate(real_missing, 1):
                log_output(f"      {i:2d}. {date.strftime('%Y-%m-%d')}")
        else:
            for i, date in enumerate(real_missing[:10], 1):
                log_output(f"      {i:2d}. {date.strftime('%Y-%m-%d')}")
            log_output(f"      ... 还有 {missing_count - 10} 个")
        return False


def verify_volume_files():
    """验证volume文件（成交额分时数据）"""
    log_output("\n📊 成交额分时数据（volume）")

    data_dir = Path("data")
    pattern = re.compile(r"volume-(\d{8})\.jsonl$")
    files = []

    for file in data_dir.glob("volume-*.jsonl"):
        match = pattern.search(file.name)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                files.append(file_date)
            except ValueError:
                pass

    if not files:
        log_output("   ❌ 未找到 volume 文件")
        return False

    log_output(f"   ✅ 文件数量：{len(files)} 个")
    log_output(f"   📅 日期范围：{min(files).strftime('%Y-%m-%d')} 至 {max(files).strftime('%Y-%m-%d')}")
    return True


def verify_warmup_completeness():
    """验证warmup数据完整性"""
    log_output("\n📊 warmup数据完整性检查")

    # warmup数据由以下组成:
    # 1. archive文件（大盘指数+关注ETF+全市场ETF成交额）
    # 2. volume文件（成交额分时）

    archive_ok = verify_archive_files()
    volume_ok = verify_volume_files()

    return archive_ok and volume_ok


def main():
    """主函数"""
    now = datetime.now()
    log_file = Path(f"logs/verify_{now.strftime('%Y-%m-%d')}.log")

    # 创建日志目录
    log_file.parent.mkdir(exist_ok=True)

    # 重定向输出到日志文件
    original_stdout = sys.stdout
    sys.stdout = open(log_file, 'a', encoding='utf-8')

    try:
        # 写入时间戳
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        log_output(f"\n{'='*80}")
        log_output(f"📊 warmup数据验证报告 - {timestamp}")
        log_output(f"{'='*80}")

        log_output(f"\n📅 warmup数据组成：")
        log_output(f"   - 大盘指数分时历史（archive）")
        log_output(f"   - 关注ETF分时历史（archive）")
        log_output(f"   - 全市场ETF成交额历史（archive + volume）")
        log_output(f"   - 保留期限：60天")

        # 验证warmup数据完整性
        warmup_ok = verify_warmup_completeness()

        # 汇总结果
        log_output(f"\n{'='*80}")
        if warmup_ok:
            log_output("✅ warmup数据验证通过")
        else:
            log_output("⚠️  warmup数据存在问题，Task #12列入回补计划")
        log_output(f"{'='*80}")

    finally:
        sys.stdout.close()
        sys.stdout = original_stdout


if __name__ == "__main__":
    main()
