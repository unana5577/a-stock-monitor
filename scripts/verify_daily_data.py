#!/usr/bin/env python3
"""
日线数据验证工具
验证：archive、ETF日线、指数日线、市场数据
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


def verify_archive_data():
    """验证大盘综合归档数据（archive）"""
    print("\n" + "="*80)
    print("📊 大盘综合归档数据（archive）")
    print("="*80)

    data_dir = Path("data")
    pattern = re.compile(r"archive-(\d{8})\.jsonl$")
    files = []

    for file in data_dir.glob("archive-*.jsonl"):
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
        print("❌ 未找到 archive 文件")
        return None

    earliest = files[0][0]
    latest = files[-1][0]
    total_size = sum(f[2] for f in files)

    print(f"✅ 文件数量：{len(files)} 个")
    print(f"📅 日期范围：{earliest.strftime('%Y-%m-%d')} 至 {latest.strftime('%Y-%m-%d')}")
    print(f"💾 总大小：{total_size / 1024:.1f} KB")

    # 检查最近60天完整性
    holidays = load_holidays()
    today = datetime.now().date()
    target_dates = get_last_n_trading_days(datetime(today.year, today.month, today.day), 60, holidays)
    existing_dates = {f[0].date() for f in files}

    real_missing = []
    holiday_missing = []

    for date in target_dates:
        date_str = date.strftime('%Y-%m-%d')
        if date.date() not in existing_dates:
            if date_str in holidays:
                holiday_missing.append(date)
            else:
                real_missing.append(date)

    print(f"\n📋 最近60交易日检查：")
    print(f"   - 真实缺失：{len(real_missing)} 个（需要回补）")
    print(f"   - 节假日缺失：{len(holiday_missing)} 个（正常）")

    if real_missing:
        print(f"\n⚠️  真实缺失日期：")
        for i, date in enumerate(real_missing[:10], 1):
            print(f"   {i:2d}. {date.strftime('%Y-%m-%d')}")
        if len(real_missing) > 10:
            print(f"   ... 还有 {len(real_missing) - 10} 个")

    return {
        'type': 'archive',
        'count': len(files),
        'earliest': earliest,
        'latest': latest,
        'missing': len(real_missing)
    }


def verify_etf_daily():
    """验证ETF日线数据"""
    print("\n" + "="*80)
    print("📊 关注ETF日线数据")
    print("="*80)

    etf_dir = Path("data/etf_daily")
    if not etf_dir.exists():
        print("❌ etf_daily/ 目录不存在")
        return None

    etf_codes = {
        'sh512480': '半导体',
        'sh516510': '云计算',
        'sh516160': '新能源',
        'sh563530': '商业航天',
        'sh515120': '创新药',
        'sh512400': '有色金属',
        'sh515880': '通讯设备',
        'sh516010': '游戏',
        'sh562500': '机器人',
    }

    results = []

    for code, name in etf_codes.items():
        file = etf_dir / f"etf_{code}.jsonl"
        if not file.exists():
            print(f"⚠️  {name}（{code}）：文件不存在")
            continue

        # 读取起止日期
        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    print(f"⚠️  {name}（{code}）：文件为空")
                    continue

                first = json.loads(lines[0])
                last = json.loads(lines[-1])
                first_date = datetime.strptime(first.get('date', ''), '%Y-%m-%d')
                last_date = datetime.strptime(last.get('date', ''), '%Y-%m-%d')

                print(f"✅ {name}（{code}）：{first_date.strftime('%Y-%m-%d')} 至 {last_date.strftime('%Y-%m-%d')}")
                results.append({
                    'code': code,
                    'name': name,
                    'first_date': first_date,
                    'last_date': last_date,
                    'count': len(lines)
                })
        except Exception as e:
            print(f"❌ {name}（{code}）：读取失败 - {e}")

    return results


def verify_index_daily():
    """验证大盘指数日线数据"""
    print("\n" + "="*80)
    print("📊 大盘指数日线数据")
    print("="*80)

    index_dir = Path("data/index_daily")
    if not index_dir.exists():
        print("❌ index_daily/ 目录不存在")
        return None

    index_codes = {
        '000001': '上证指数',
        '399001': '深证成指',
        '399006': '创业板指',
        '000688': '科创板指',
    }

    results = []

    for code, name in index_codes.items():
        file = index_dir / f"index_{code}.jsonl"
        if not file.exists():
            print(f"⚠️  {name}（{code}）：文件不存在")
            continue

        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    print(f"⚠️  {name}（{code}）：文件为空")
                    continue

                first = json.loads(lines[0])
                last = json.loads(lines[-1])
                first_date = datetime.strptime(first.get('date', ''), '%Y-%m-%d')
                last_date = datetime.strptime(last.get('date', ''), '%Y-%m-%d')

                print(f"✅ {name}（{code}）：{first_date.strftime('%Y-%m-%d')} 至 {last_date.strftime('%Y-%m-%d')}")
                results.append({
                    'code': code,
                    'name': name,
                    'first_date': first_date,
                    'last_date': last_date,
                    'count': len(lines)
                })
        except Exception as e:
            print(f"❌ {name}（{code}）：读取失败 - {e}")

    return results


def verify_market_data():
    """验证市场数据（涨跌家数、市场成交额、ETF成交额）"""
    print("\n" + "="*80)
    print("📊 市场数据")
    print("="*80)

    market_dir = Path("data/market")
    if not market_dir.exists():
        print("❌ market/ 目录不存在")
        return None

    files = {
        '涨跌家数': 'breadth-history.jsonl',
        '市场成交额': 'market-amount-daily.jsonl',
        'ETF成交额': 'etf-amount-daily.jsonl',
    }

    results = {}

    for name, filename in files.items():
        file = market_dir / filename
        if not file.exists():
            print(f"⚠️  {name}：{filename} 不存在")
            continue

        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if not lines:
                    print(f"⚠️  {name}：文件为空")
                    continue

                first = json.loads(lines[0])
                last = json.loads(lines[-1])

                if 'date' in first:
                    first_date = first['date']
                    last_date = last['date']
                elif 'timestamp' in first:
                    first_date = datetime.fromtimestamp(first['timestamp'] / 1000).strftime('%Y-%m-%d')
                    last_date = datetime.fromtimestamp(last['timestamp'] / 1000).strftime('%Y-%m-%d')
                else:
                    first_date = 'N/A'
                    last_date = 'N/A'

                print(f"✅ {name}：{first_date} 至 {last_date}（{len(lines)} 条记录）")
                results[name] = {
                    'filename': filename,
                    'first_date': first_date,
                    'last_date': last_date,
                    'count': len(lines)
                }
        except Exception as e:
            print(f"❌ {name}：读取失败 - {e}")

    return results


def main():
    """主函数"""
    print("="*80)
    print("🔍 日线数据验证工具".center(80))
    print("="*80)
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 验证各类数据
    archive_result = verify_archive_data()
    etf_result = verify_etf_daily()
    index_result = verify_index_daily()
    market_result = verify_market_data()

    # 汇总报告
    print("\n" + "="*80)
    print("📋 验证汇总")
    print("="*80)

    print(f"\n✅ 验证完成：")
    print(f"   - 大盘综合：{'通过' if archive_result else '失败'}")
    print(f"   - 关注ETF：{'通过' if etf_result else '失败'}")
    print(f"   - 大盘指数：{'通过' if index_result else '失败'}")
    print(f"   - 市场数据：{'通过' if market_result else '失败'}")

    print(f"\n⚠️  待处理任务：")
    if archive_result and archive_result['missing'] > 0:
        print(f"   - #12：大盘综合 archive 数据回补（{archive_result['missing']} 天缺失）")
    if market_result:
        if '市场成交额' in market_result:
            print(f"   - #10：市场成交额数据修复")
        print(f"   - #11：AI实时接口数据溯源分析")

    print("\n" + "="*80)


if __name__ == "__main__":
    main()
