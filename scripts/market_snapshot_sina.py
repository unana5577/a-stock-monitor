#!/usr/bin/env python3
"""
全市场快照数据采集 - 合并涨跌家数和ETF成交额
开盘时间每5分钟执行一次（9:30-11:30, 13:00-15:00）
同时获取：
1. A股涨跌家数（stock_zh_a_spot）
2. 全市场ETF成交额（fund_etf_category_sina）
"""

import akshare as ak
import json
from pathlib import Path
from datetime import datetime, time


def is_trading_time():
    """判断是否是交易时间（9:30-11:30, 13:00-15:00）"""
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()

    # 周末不交易
    if weekday >= 5:  # 5=周六, 6=周日
        return False

    # 上午：9:30-11:30
    morning_start = time(9, 30)
    morning_end = time(11, 30)

    # 下午：13:00-15:00
    afternoon_start = time(13, 0)
    afternoon_end = time(15, 0)

    return (morning_start <= current_time <= morning_end or
            afternoon_start <= current_time <= afternoon_end)


def get_cached_snapshot():
    """获取缓存的快照数据（非交易时间使用）"""
    breadth_file = Path("data/market/breadth-cache.json")

    if not breadth_file.exists():
        return None

    try:
        with open(breadth_file, 'r', encoding='utf-8') as f:
            breadth = json.load(f)

        etf_file = Path("data/market/etf-amount-daily.jsonl")
        etf = None
        if etf_file.exists():
            with open(etf_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if lines:
                    etf = json.loads(lines[-1].strip())

        return {
            "timestamp": datetime.now().isoformat(),
            "breadth": breadth,
            "etf": etf,
            "cached": True
        }
    except Exception as e:
        print(f"  ⚠️  读取缓存失败: {e}")
        return None


def get_latest_etf_amount():
    """获取最新的ETF成交额记录"""
    file_path = Path("data/market/etf-amount-daily.jsonl")
    if not file_path.exists():
        return None

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if not lines:
        return None

    try:
        return json.loads(lines[-1].strip())
    except:
        return None


def fetch_market_snapshot():
    """获取全市场快照数据"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始获取全市场快照数据...")

    # 1. 获取A股涨跌家数（约21秒）
    print("  1. 获取A股涨跌家数...")
    try:
        stocks_df = ak.stock_zh_a_spot()
        up = stocks_df[stocks_df['涨跌幅'] > 0].shape[0]
        down = stocks_df[stocks_df['涨跌幅'] < 0].shape[0]
        flat = stocks_df[stocks_df['涨跌幅'] == 0].shape[0]
        total = up + down + flat
        ratio = up / down if down > 0 else float('inf')

        breadth = {
            "up": int(up),
            "down": int(down),
            "flat": int(flat),
            "total": int(total),
            "ratio": round(float(ratio), 2),
            "sentiment": "亢奋" if ratio > 2 else ("恐慌" if ratio < 0.3 else "正常")
        }
        print(f"     ✅ 涨跌家数: 上涨{up} / 下跌{down} / 平盘{flat}，情绪: {breadth['sentiment']}")
    except Exception as e:
        print(f"     ❌ 获取涨跌家数失败: {e}")
        breadth = None

    # 2. 获取ETF成交额（<1秒）
    print("  2. 获取ETF成交额...")
    try:
        etf_df = ak.fund_etf_category_sina(symbol="ETF基金")
        etf_amount = etf_df['成交额'].fillna(0).astype(float).sum()
        etf_count = len(etf_df)

        etf = {
            "amount": round(float(etf_amount), 2),  # 元
            "amount_yi": round(float(etf_amount) / 100000000, 2),  # 亿元
            "count": int(etf_count)
        }
        print(f"     ✅ ETF成交额: {etf['amount_yi']:.2f}亿，ETF数量: {etf_count}")
    except Exception as e:
        print(f"     ❌ 获取ETF成交额失败: {e}")
        etf = None

    return {
        "timestamp": datetime.now().isoformat(),
        "breadth": breadth,
        "etf": etf
    }


def save_snapshot(data):
    """保存快照数据"""
    dir_path = Path("data/market")
    dir_path.mkdir(parents=True, exist_ok=True)

    # 1. 保存涨跌家数缓存
    if data.get("breadth"):
        breadth_file = dir_path / "breadth-cache.json"
        with open(breadth_file, 'w', encoding='utf-8') as f:
            json.dump(data["breadth"], f, ensure_ascii=False, indent=2)
        print(f"  💾 涨跌家数已缓存到: {breadth_file}")

    # 2. 追加ETF成交额到历史文件
    if data.get("etf"):
        etf_file = dir_path / "etf-amount-daily.jsonl"
        today = datetime.now().strftime("%Y-%m-%d")

        # 检查今天是否已有记录
        existing_records = []
        if etf_file.exists():
            with open(etf_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        existing_records.append(record)
                    except:
                        pass

        # 更新今天的记录（如果存在则替换，否则追加）
        today_record = {
            "date": today,
            "amount": data["etf"]["amount"],
            "amount_yi": data["etf"]["amount_yi"],
            "count": data["etf"]["count"],
            "timestamp": data["timestamp"]
        }

        # 移除今天的旧记录
        existing_records = [r for r in existing_records if r.get("date") != today]
        existing_records.append(today_record)

        # 按日期排序并写回
        existing_records.sort(key=lambda x: x.get("date", ""))
        with open(etf_file, 'w', encoding='utf-8') as f:
            for record in existing_records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

        print(f"  💾 ETF成交额已保存到: {etf_file}")


def main():
    """主函数"""
    print("=" * 60)
    print("全市场快照数据采集")
    print("=" * 60)

    # 判断是否是交易时间
    if not is_trading_time():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 非交易时间，返回缓存数据")
        snapshot = get_cached_snapshot()
        if snapshot:
            print("  ✅ 使用缓存数据")
        else:
            print("  ❌ 缓存数据不可用")
        return snapshot

    # 交易时间：获取实时数据
    snapshot = fetch_market_snapshot()

    # 保存数据
    save_snapshot(snapshot)

    print("=" * 60)
    print("✅ 快照数据采集完成")
    print("=" * 60)

    # 返回结果供其他程序调用
    return snapshot


if __name__ == "__main__":
    main()
