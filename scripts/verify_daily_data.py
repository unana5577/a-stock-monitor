#!/usr/bin/env python3
"""
日线数据验证工具 - 时间感知版本
运行时间: 09:15, 15:30
检查内容: 最新数据日期（盘中T-1，盘后T）、断点检查
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


def get_last_trading_day(now, holidays):
    """获取最近的交易日"""
    current = now
    while not is_trading_day(current, holidays):
        current -= timedelta(days=1)
    return current


def get_expected_latest_date(now, holidays):
    """根据当前时间判断期望的最新数据日期"""
    hour = now.hour

    # 15:30之后: 应该有当天的日线数据
    if hour >= 15:
        if is_trading_day(now, holidays):
            return now.date(), "盘后"
        else:
            return get_last_trading_day(now, holidays).date(), "非交易日"
    else:
        # 盘中: 最新数据应该是T-1
        return get_last_trading_day(now - timedelta(days=1), holidays).date(), "盘中"


def log_output(message):
    """输出到stdout和日志"""
    print(message)


def verify_etf_daily(now, expected_date, period):
    """验证ETF日线数据"""
    log_output("\n📊 关注ETF日线")

    etf_codes = {
        '512480': '半导体',
        '516510': '云计算',
        '516160': '新能源',
        '563530': '商业航天',
        '515120': '创新药',
        '512400': '有色金属',
        '515880': '通讯设备',
        '516010': '游戏',
        '562500': '机器人',
    }

    results = []
    expected_date_str = expected_date.strftime('%Y-%m-%d')

    for code, name in etf_codes.items():
        file = Path(f"data/etf_daily/etf_{code}.jsonl")

        if not file.exists():
            # 检查是否是路径问题
            if not Path("data/etf_daily").exists():
                log_output(f"   ❌ {name}（{code}）：data/etf_daily/ 目录不存在")
            else:
                log_output(f"   ❌ {name}（{code}）：文件不存在")
            results.append(False)
            continue

        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    log_output(f"   ⚠️  {name}（{code}）：文件为空")
                    results.append(False)
                    continue

                last = json.loads(lines[-1])
                last_date_str = last.get('date', '')

                if last_date_str == expected_date_str:
                    log_output(f"   ✅ {name}（{code}）：最新 {last_date_str}（{period}正常）")
                    results.append(True)
                else:
                    log_output(f"   ⚠️  {name}（{code}）：最新 {last_date_str}（期望 {expected_date_str}）")
                    results.append(False)

        except Exception as e:
            log_output(f"   ❌ {name}（{code}）：读取失败 - {e}")
            results.append(False)

    return all(results)


def verify_index_daily(now, expected_date, period):
    """验证大盘指数日线数据"""
    log_output("\n📊 大盘指数日线")

    index_codes = {
        '000001': '上证指数',
        '399001': '深证成指',
        '399006': '创业板指',
        '000688': '科创板指',
    }

    results = []
    expected_date_str = expected_date.strftime('%Y-%m-%d')

    for code, name in index_codes.items():
        file = Path(f"data/index_daily/index_{code}.jsonl")

        if not file.exists():
            log_output(f"   ❌ {name}（{code}）：文件不存在")
            results.append(False)
            continue

        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    log_output(f"   ⚠️  {name}（{code}）：文件为空")
                    results.append(False)
                    continue

                last = json.loads(lines[-1])
                last_date_str = last.get('date', '')

                if last_date_str == expected_date_str:
                    log_output(f"   ✅ {name}（{code}）：最新 {last_date_str}（{period}正常）")
                    results.append(True)
                else:
                    log_output(f"   ⚠️  {name}（{code}）：最新 {last_date_str}（期望 {expected_date_str}）")
                    results.append(False)

        except Exception as e:
            log_output(f"   ❌ {name}（{code}）：读取失败 - {e}")
            results.append(False)

    return all(results)


def verify_market_data(now, expected_date, period):
    """验证市场数据"""
    log_output("\n📊 市场数据")

    files = {
        '涨跌家数': 'breadth-history.jsonl',
        '市场成交额': 'market-amount-daily.jsonl',
        'ETF成交额': 'etf-amount-daily.jsonl',
    }

    results = []
    expected_date_str = expected_date.strftime('%Y-%m-%d')

    for name, filename in files.items():
        file = Path(f"data/market/{filename}")

        if not file.exists():
            log_output(f"   ❌ {name}：文件不存在")
            results.append(False)
            continue

        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    log_output(f"   ⚠️  {name}：文件为空")
                    results.append(False)
                    continue

                last = json.loads(lines[-1])

                if 'date' in last:
                    last_date_str = last['date']
                elif 'timestamp' in last:
                    last_date_str = datetime.fromtimestamp(last['timestamp'] / 1000).strftime('%Y-%m-%d')
                else:
                    log_output(f"   ⚠️  {name}：无法解析日期")
                    results.append(False)
                    continue

                if last_date_str == expected_date_str:
                    log_output(f"   ✅ {name}：最新 {last_date_str}（{period}正常）")
                    results.append(True)
                else:
                    log_output(f"   ⚠️  {name}：最新 {last_date_str}（期望 {expected_date_str}）")
                    results.append(False)

        except Exception as e:
            log_output(f"   ❌ {name}：读取失败 - {e}")
            results.append(False)

    return all(results)


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
        log_output(f"📊 日线数据验证报告 - {timestamp}")
        log_output(f"{'='*80}")

        # 获取期望的最新数据日期
        holidays = load_holidays()
        expected_date, period = get_expected_latest_date(now, holidays)

        log_output(f"\n📅 检查时段：{period}")
        log_output(f"📅 期望最新日期：{expected_date.strftime('%Y-%m-%d')}")

        # 验证各类日线数据
        etf_ok = verify_etf_daily(now, expected_date, period)
        index_ok = verify_index_daily(now, expected_date, period)
        market_ok = verify_market_data(now, expected_date, period)

        # 汇总结果
        log_output(f"\n{'='*80}")
        if etf_ok and index_ok and market_ok:
            log_output("✅ 日线数据验证通过")
        else:
            log_output("⚠️  日线数据存在问题")
        log_output(f"{'='*80}")

    finally:
        sys.stdout.close()
        sys.stdout = original_stdout


if __name__ == "__main__":
    main()
