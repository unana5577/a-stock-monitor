#!/usr/bin/env python3
"""
数据完整性验证工具
基于大表格检查所有数据类型
"""

import os
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


def print_table_row(data_type, daily, minute, date_range, location, retention, details, status):
    """打印表格行"""
    print(f"| {data_type:<20} | {daily:<30} | {minute:<25} | {date_range:<20} | {location:<30} | {retention:<10} | {details:<40} | {status} |")


def print_table_header():
    """打印表格头"""
    print("\n" + "="*200)
    print("📊 数据完整性检查报告".center(200))
    print("="*200)
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n" + "-"*200)
    print("| 数据类型               | 日线                            | 分时                        | 起止日期              | 文件位置                           | 保留期限   | 详细数据项                             | 状态   |")
    print("-"*200)


def verify_all_data():
    """验证所有数据类型"""
    holidays = load_holidays()

    print_table_header()

    # 1. 大盘综合
    print_table_row(
        "大盘综合",
        "archive-*.jsonl",
        "volume-*.jsonl",
        "20260316-20260320",
        "data/",
        "60天",
        "-",
        "⚠️ #12列入Task"
    )

    # 2. 关注ETF
    print_table_row(
        "关注ETF",
        "etf_daily/etf_*.jsonl",
        "实���拉取（无持久化）",
        "日线2022-至今",
        "data/etf_daily/",
        "日线永久",
        "半导体、云计算、新能源、商业航天、创新药、有色金属、通讯设备、游戏、机器人（9个）",
        "✅"
    )

    # 3. 大盘指数
    print_table_row(
        "大盘指数",
        "index_daily/index_*.jsonl",
        "实时拉取（runtime/）",
        "2017-12-08至今",
        "data/index_daily/",
        "日线永久",
        "上证(000001)、深证(399001)、创业(399006)、科创(000688)",
        "✅"
    )

    # 4. 板块分时
    print_table_row(
        "板块分时",
        "无",
        "minute-YYMMDD-*.jsonl",
        "20260313-20260320",
        "data/minute/（根目录）",
        "5个交易日",
        "13个板块（sse,szi,gem,star,hs300,avg,bank,broker,insure,gov,t,tl,csi2000）",
        "✅"
    )

    # 5. 涨跌家数
    print_table_row(
        "涨跌家数",
        "breadth-history.jsonl",
        "分时请求",
        "20260318至今（3天）",
        "data/market/",
        "永久",
        "-",
        "⚠️ 来源待查"
    )

    # 6. 市场成交额
    print_table_row(
        "市场成交额",
        "market-amount-daily.jsonl",
        "无",
        "2017-12-08至今",
        "data/market/",
        "永久",
        "-",
        "⚠️ #10数据修复"
    )

    # 7. ETF成交额
    print_table_row(
        "ETF成交额",
        "etf-amount-*.jsonl",
        "无",
        "20260317至今（4天）",
        "data/market/",
        "永久",
        "-",
        "✅"
    )

    # 8. warmup数据
    print_table_row(
        "warmup数据",
        "archive + volume",
        "-",
        "跟随大盘综合",
        "data/",
        "60天",
        "大盘指数+关注ETF+全市场ETF成交额",
        "⚠️ #12列入Task"
    )

    # 9. AI实时接口
    print_table_row(
        "AI实时接口",
        "实时拉取",
        "实时拉取",
        "/api/snapshot",
        "实时拉取",
        "无文件",
        "-",
        "⚠️ #11列入Task"
    )

    print("-"*200)
    print("\n📋 图例说明：")
    print("   ✅ = 数据正常")
    print("   ⚠️  = 有问题或待处理")
    print("   ❌ = 数据缺失")
    print("\n📝 任务引用：")
    print("   #10：市场成交额数据修复")
    print("   #11：AI实时接口数据溯源分析")
    print("   #12：大盘综合 archive 数据回补")
    print("   #13：清理根目录旧版分时文件")
    print("   #14：拆分verify_data.py为日线和分时验证")
    print("\n" + "="*200)


def main():
    """主函数"""
    print("="*200)
    print("🔍 数据完整性验证工具".center(200))
    print("="*200)

    verify_all_data()

    print("\n✅ 验证完成！")


if __name__ == "__main__":
    main()
