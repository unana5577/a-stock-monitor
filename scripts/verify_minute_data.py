#!/usr/bin/env python3
"""
分时数据验证工具 - 时间感知版本
运行时间: 09:31, 13:01
检查内容: 大盘指数分时、板块分时数据点数
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


def get_expected_points(now):
    """根据当前时间判断期望的数据点数"""
    hour = now.hour
    minute = now.minute

    # 早盘收盘后 (11:30之后): 应该有120点或121点(包含集合竞价)
    if hour > 11 or (hour == 11 and minute >= 30):
        # 如果是下午,检查全天数据(15:00后应有240点或241点)
        if hour >= 15:
            return 240, "全天"
        else:
            return 120, "早盘"

    # 早盘中: 暂不严格要求点数
    return None, "交易中"


def log_output(message):
    """输出到stdout和日志"""
    print(message)


def verify_index_minute(now, expected_points, period):
    """验证大盘指数分时数据"""
    log_output("\n📊 大盘指数分时")

    sectors = {
        'sse': '上证指数',
        'szi': '深证成指',
        'gem': '创业板指',
        'star': '科创板指',
        'hs300': '沪深300'
    }

    today = now.strftime('%Y%m%d')
    results = []

    for code, name in sectors.items():
        file = Path(f"data/minute-{today}-{code}.jsonl")

        if not file.exists():
            log_output(f"   ❌ {name}（{code}）：文件不存在")
            results.append(False)
            continue

        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                point_count = len(lines)

                if expected_points:
                    # 允许+1点（包含集合竞价）
                    if point_count == expected_points or point_count == expected_points + 1:
                        log_output(f"   ✅ {name}（{code}）：{point_count}点（{period}）")
                        results.append(True)
                    else:
                        log_output(f"   ⚠️  {name}（{code}）：{point_count}点（期望{expected_points}点）")
                        results.append(False)
                else:
                    log_output(f"   📊 {name}（{code}）：{point_count}点（交易中）")
                    results.append(True)

        except Exception as e:
            log_output(f"   ❌ {name}（{code}）：读取失败 - {e}")
            results.append(False)

    return all(results)


def verify_sector_minute(now, expected_points, period):
    """验证板块分时数据"""
    log_output("\n📊 板块分时")

    sectors = {
        'bank': '银行',
        'broker': '证券',
        'insure': '保险'
    }

    today = now.strftime('%Y%m%d')
    results = []

    for code, name in sectors.items():
        file = Path(f"data/minute-{today}-{code}.jsonl")

        if not file.exists():
            # 检查根目录是否存在该文件
            data_dir = Path("data")
            matching_files = list(data_dir.glob(f"minute-{today}-{code}.jsonl"))
            if matching_files:
                file = matching_files[0]
            else:
                log_output(f"   ❌ {name}（{code}）：文件不存在")
                results.append(False)
                continue

        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                point_count = len(lines)

                if expected_points:
                    # 允许+1点（包含集合竞价）
                    if point_count == expected_points or point_count == expected_points + 1:
                        log_output(f"   ✅ {name}（{code}）：{point_count}点（{period}）")
                        results.append(True)
                    else:
                        log_output(f"   ⚠️  {name}（{code}）：{point_count}点（期望{expected_points}点）")
                        results.append(False)
                else:
                    log_output(f"   📊 {name}（{code}）：{point_count}点（交易中）")
                    results.append(True)

        except Exception as e:
            log_output(f"   ❌ {name}（{code}）：读取失败 - {e}")
            results.append(False)

    return all(results)


def verify_csi2000_minute(now, expected_points, period):
    """验证中证2000分时数据"""
    log_output("\n📊 中证2000分时")

    today = now.strftime('%Y%m%d')
    file = Path(f"data/minute-{today}-csi2000.jsonl")

    if not file.exists():
        log_output(f"   ❌ 中证2000：文件不存在")
        return False

    try:
        with open(file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            point_count = len(lines)

            if expected_points:
                if point_count == expected_points:
                    log_output(f"   ✅ 中证2000：{point_count}点（{period}）")
                    return True
                else:
                    log_output(f"   ⚠️  中证2000：{point_count}点（期望{expected_points}点）")
                    return False
            else:
                log_output(f"   📊 中证2000：{point_count}点（交易中）")
                return True

    except Exception as e:
        log_output(f"   ❌ 中证2000：读取失败 - {e}")
        return False


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
        log_output(f"📊 分时数据验证报告 - {timestamp}")
        log_output(f"{'='*80}")

        # 判断是否为交易日
        holidays = load_holidays()
        if not is_trading_day(now, holidays):
            log_output("\n⚠️  今天不是交易日，跳过分时数据检查")
            return

        # 获取期望的数据点数
        expected_points, period = get_expected_points(now)

        if expected_points:
            log_output(f"\n📅 检查时段：{period}（期望{expected_points}个数据点）")
        else:
            log_output(f"\n📅 检查时段：交易中（不严格检查点数）")

        # 验证各类分时数据
        index_ok = verify_index_minute(now, expected_points, period)
        sector_ok = verify_sector_minute(now, expected_points, period)
        csi2000_ok = verify_csi2000_minute(now, expected_points, period)

        # 汇总结果
        log_output(f"\n{'='*80}")
        if index_ok and sector_ok and csi2000_ok:
            log_output("✅ 分时数据验证通过")
        else:
            log_output("⚠️  分时数据存在问题")
        log_output(f"{'='*80}")

    finally:
        sys.stdout.close()
        sys.stdout = original_stdout


if __name__ == "__main__":
    main()
