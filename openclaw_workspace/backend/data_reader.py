# -*- coding: utf-8 -*-
"""
数据读取示例
展示如何读取 Trae 项目的数据
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional


# ============================================
# 数据路径配置
# ============================================

DATA_DIR = os.path.expanduser("~/股票项目/data/trae-data")


# ============================================
# 读取分时数据
# ============================================

def read_minute_data(date: str, symbol: str) -> List[Dict]:
    """
    读取分时数据

    Args:
        date: 日期（格式：YYYY-MM-DD 或 YYYYMMDD）
        symbol: 指数代码（如 sse, szi, gem, star, hs300, csi2000, avg, bank, broker, insure, t, tl）

    Returns:
        分时数据列表

    Example:
        >>> data = read_minute_data("2026-02-24", "sse")
        >>> print(f"获取到 {len(data)} 条分时数据")
        >>> print(data[0])  # {'time': '09:31', 'price': 3350.12, 'avg': 3348.5}
    """
    # 标准化日期格式
    date_str = date.replace("-", "")

    # 构建文件路径
    filename = f"minute-{date_str}-{symbol}.jsonl"
    filepath = os.path.join(DATA_DIR, filename)

    if not os.path.exists(filepath):
        print(f"⚠️  文件不存在: {filepath}")
        return []

    data = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # 解析 JSONL 格式
                parts = json.loads(line)
                if len(parts) >= 3:
                    time_str = parts[0]  # "2026-02-13 09:31"
                    price = float(parts[1])
                    avg_price = float(parts[2])

                    # 提取时间部分
                    time_only = time_str.split(" ")[1] if " " in time_str else time_str

                    data.append({
                        "time": time_only,
                        "price": price,
                        "avg": avg_price
                    })
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return []

    return data


# ============================================
# 读取日线数据
# ============================================

def read_daily_data(date: str) -> Dict:
    """
    读取日线数据

    Args:
        date: 日期（格式：YYYY-MM-DD 或 YYYYMMDD）

    Returns:
        日线数据字典

    Example:
        >>> data = read_daily_data("2026-02-24")
        >>> print(f"数据日期: {data['day']}")
        >>> print(f"上证指数历史数据: {len(data['series']['sse'])} 条")
    """
    # 标准化日期格式
    date_str = date.replace("-", "")

    # 构建文件路径
    filename = f"overview-history-{date_str}.json"
    filepath = os.path.join(DATA_DIR, filename)

    if not os.path.exists(filepath):
        print(f"⚠️  文件不存在: {filepath}")
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return {}


# ============================================
# 读取涨跌家数
# ============================================

def read_market_breadth(date: str) -> Dict:
    """
    读取涨跌家数

    Args:
        date: 日期（格式：YYYY-MM-DD 或 YYYYMMDD）

    Returns:
        涨跌家数字典

    Example:
        >>> breadth = read_market_breadth("2026-02-24")
        >>> print(f"上涨: {breadth['up']}, 下跌: {breadth['down']}")
    """
    # 标准化日期格式
    date_str = date.replace("-", "")

    # 构建文件路径
    filename = f"market-breadth-{date_str}.json"
    filepath = os.path.join(DATA_DIR, filename)

    if not os.path.exists(filepath):
        print(f"⚠️  文件不存在: {filepath}")
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"❌ 读取失败: {e}")
        return {}


# ============================================
# 获取所有可用的指数列表
# ============================================

def get_available_symbols() -> List[str]:
    """
    获取所有可用的指数/板块代码

    Returns:
        指数代码列表

    Example:
        >>> symbols = get_available_symbols()
        >>> print(symbols)
        ['sse', 'szi', 'gem', 'star', 'hs300', 'csi2000', 'avg', 'bank', 'broker', 'insure', 't', 'tl']
    """
    return [
        "sse",       # 上证指数
        "szi",       # 深证成指
        "gem",       # 创业板
        "star",      # 科创板
        "hs300",     # 沪深300
        "csi2000",   # 中证2000
        "avg",       # 平均股价
        "bank",      # 银行板块
        "broker",    # 券商板块
        "insure",    # 保险板块
        "t",         # 国债
        "tl"         # 金融板块
    ]


# ============================================
# 获取最新数据日期
# ============================================

def get_latest_date() -> Optional[str]:
    """
    获取最新数据日期

    Returns:
        最新日期（格式：YYYY-MM-DD）

    Example:
        >>> latest = get_latest_date()
        >>> print(f"最新数据日期: {latest}")
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # 检查今天的数据是否存在
    today_str = today.replace("-", "")
    filename = f"overview-history-{today_str}.json"
    filepath = os.path.join(DATA_DIR, filename)

    if os.path.exists(filepath):
        return today

    # 如果今天的数据不存在，返回昨天
    from datetime import timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return yesterday


# ============================================
# 测试代码
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("数据读取测试")
    print("=" * 60)

    # 1. 获取最新日期
    latest_date = get_latest_date()
    print(f"\n📅 最新数据日期: {latest_date}")

    # 2. 读取分时数据
    print(f"\n📊 读取上证指数分时数据...")
    minute_data = read_minute_data(latest_date, "sse")
    if minute_data:
        print(f"✅ 获取到 {len(minute_data)} 条分时数据")
        print(f"   第一条: {minute_data[0]}")
        print(f"   最后一条: {minute_data[-1]}")

    # 3. 读取日线数据
    print(f"\n📈 读取日线数据...")
    daily_data = read_daily_data(latest_date)
    if daily_data:
        print(f"✅ 数据日期: {daily_data['day']}")
        print(f"   指数列表: {list(daily_data['series'].keys())}")
        if 'sse' in daily_data['series']:
            sse_data = daily_data['series']['sse']
            print(f"   上证指数数据: {len(sse_data)} 条")
            print(f"   最新数据: {sse_data[-1]}")

    # 4. 读取涨跌家数
    print(f"\n📉 读取涨跌家数...")
    breadth = read_market_breadth(latest_date)
    if breadth:
        print(f"✅ 上涨: {breadth['up']}, 下跌: {breadth['down']}, 平盘: {breadth['flat']}")

    # 5. 获取所有可用指数
    print(f"\n📋 所有可用指数:")
    symbols = get_available_symbols()
    for i, symbol in enumerate(symbols, 1):
        print(f"   {i}. {symbol}")

    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)
