#!/usr/bin/env python3
"""
简单的ETF数据更新脚本 - 直接写入etf_daily
"""
import akshare as ak
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from io import StringIO

# ETF配置
ETF_CONFIG = {
    "sh512480": "半导体",
    "sh516160": "新能源",
    "sh512400": "有色金属",
    "sh515880": "通讯设备",
    "sh515120": "创新药",
    "sh516010": "游戏",
    "sh516510": "云计算",
    "sh562500": "机器人",
    "sh563530": "商业航天",
}

def is_trading_day(date_str):
    """判断是否交易日"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() >= 5:  # 周末
        return False
    return True

def get_latest_trading_day():
    """获取最新交易日"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    today_str = now.strftime("%Y-%m-%d")

    # 非交易时间（15:01后），可以获取今天
    hour = now.hour
    minute = now.minute
    total_minutes = hour * 60 + minute

    if total_minutes <= 901:  # 15:01 之前，只能到昨天
        # 回退到昨天
        for i in range(1, 8):
            prev_date = now - timedelta(days=i)
            prev_str = prev_date.strftime("%Y-%m-%d")
            if is_trading_day(prev_str):
                return prev_str

    # 非交易时间，可以到今天
    if is_trading_day(today_str):
        return today_str

    # 回退
    for i in range(1, 8):
        prev_date = now - timedelta(days=i)
        prev_str = prev_date.strftime("%Y-%m-%d")
        if is_trading_day(prev_str):
            return prev_str

    return today_str

def get_latest_date_from_file(etf_code):
    """从文件获取最新日期"""
    filepath = f"data/etf_daily/etf_{etf_code}.jsonl"
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r') as f:
        lines = f.readlines()
        if lines:
            last_line = json.loads(lines[-1])
            return last_line.get('date')
    return None

def fetch_etf_data(etf_code, start_date, end_date):
    """请求ETF数据"""
    try:
        clean_code = etf_code.replace('sh', '').replace('sz', '')

        # 转换日期格式
        start = start_date.replace('-', '')
        end = end_date.replace('-', '')

        old_stderr = sys.stderr
        sys.stderr = StringIO()

        df = ak.fund_etf_hist_em(
            symbol=clean_code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq"
        )

        sys.stderr = old_stderr

        if df is None or df.empty:
            return []

        data = []
        for _, row in df.iterrows():
            try:
                data.append({
                    "date": str(row.get('日期', '')),
                    "open": float(row.get('开盘', 0)),
                    "close": float(row.get('收盘', 0)),
                    "high": float(row.get('最高', 0)),
                    "low": float(row.get('最低', 0)),
                    "volume": float(row.get('成交量', 0)),
                    "amount": float(row.get('成交额', 0)),
                    "pct": float(row.get('涨跌幅', 0))
                })
            except:
                continue

        return data
    except Exception as e:
        print(f"  请求异常: {str(e)[:60]}")
        return []

def calculate_missing_days(from_date, to_date):
    """计算缺失交易日"""
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        to_dt = datetime.strptime(to_date, "%Y-%m-%d")

        missing = []
        current = from_dt + timedelta(days=1)

        while current <= to_dt:
            date_str = current.strftime("%Y-%m-%d")
            if is_trading_day(date_str):
                missing.append(date_str)
            current += timedelta(days=1)

        return missing
    except:
        return []

def append_to_file(etf_code, new_data):
    """追加数据到文件（幂等）"""
    filepath = f"data/etf_daily/etf_{etf_code}.jsonl"

    # 读取现有日期
    existing_dates = set()
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    if item.get('date'):
                        existing_dates.add(item['date'])
                except:
                    pass

    # 过滤已存在
    to_append = [item for item in new_data if item.get('date') not in existing_dates]

    if not to_append:
        return 0

    # 追加
    with open(filepath, 'a') as f:
        for item in to_append:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

    return len(to_append)

# 主程序
def main():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    today_str = now.strftime("%Y-%m-%d")

    # 判断是否在交易时间
    hour = now.hour
    minute = now.minute
    total_minutes = hour * 60 + minute
    is_trading_hours = total_minutes <= 901  # 15:01 之前

    print(f"当前时间: {today_str} {hour:02d}:{minute:02d}")
    print(f"交易时段: {'是' if is_trading_hours else '否'} (>15:01)")
    print(f"最新可交易日: {get_latest_trading_day()}")
    print()

    latest_available = get_latest_trading_day()

    # 处理每个ETF
    for etf_code, etf_name in ETF_CONFIG.items():
        print(f"处理 {etf_name} ({etf_code})...")

        # 读取本地最新日期
        local_latest = get_latest_date_from_file(etf_code)
        print(f"  本地最新: {local_latest}")

        if local_latest and local_latest >= latest_available:
            print(f"  ✅ 数据已最新")
            continue

        # 计算缺失交易日
        missing_days = calculate_missing_days(local_latest or "2025-01-01", latest_available)
        if not missing_days:
            print(f"  ✅ 无缺失交易日")
            continue

        print(f"  缺失交易日: {missing_days}")

        # 请求数据
        data = fetch_etf_data(etf_code, missing_days[0], missing_days[-1])
        if not data:
            print(f"  ❌ 请求失败")
            continue

        # 写入文件
        added = append_to_file(etf_code, data)
        print(f"  ✅ 追加 {added} 条数据")

        # 验证
        new_latest = get_latest_date_from_file(etf_code)
        print(f"  最新日期: {new_latest}")

        print()

if __name__ == "__main__":
    main()
