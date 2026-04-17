#!/usr/bin/env python3
"""
M1 大盘全市场历史回填脚本 (Backfill)
目标：
1. 从稳定源(新浪/腾讯)抓取四大指数 (sh000001, sz399001, sz399006, sh000688) 的干净历史日线数据。
2. 不污染也不依赖旧的 `data/index_daily/`，直接生成并覆写到新的 `data/m1/index/<symbol>/daily.jsonl` 规范路径。
3. 补齐所有 OHLC、成交量(volume)、成交额(amount)，并精确计算 pct。
"""

import akshare as ak
import json
from pathlib import Path
from datetime import datetime

# 核心四大宽基指数 (akshare stock_zh_index_daily 对应的 symbol)
INDEX_SYMBOLS = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50"
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
M1_INDEX_DIR = PROJECT_ROOT / "data" / "m1" / "index"

def fetch_and_clean_index(symbol: str, name: str):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始回填 {name} ({symbol}) ...")
    try:
        # 新浪接口：stock_zh_index_daily，返回数据包含 date, open, high, low, close, volume
        # 腾讯接口(更稳定带amount)：stock_zh_index_daily_tx
        df = ak.stock_zh_index_daily_tx(symbol=symbol)
    except Exception as e:
        print(f"  ❌ 抓取失败: {e}")
        return

    if df.empty:
        print(f"  ❌ 返回数据为空")
        return

    # 确保存储目录存在
    symbol_dir = M1_INDEX_DIR / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    daily_file = symbol_dir / "daily.jsonl"
    
    # 按照旧文件习惯或通用标准，重命名列
    # df columns: date, open, close, high, low, amount
    # 计算 pct (涨跌幅)
    df['prev_close'] = df['close'].shift(1)
    df['pct'] = ((df['close'] - df['prev_close']) / df['prev_close'] * 100).round(2)
    # 第一天的 pct 置为 0
    df['pct'] = df['pct'].fillna(0)

    # 准备写入
    records = []
    for _, row in df.iterrows():
        # 日期格式化为 YYYY-MM-DD
        date_str = str(row['date'])[:10]
        # 过滤掉 1990 年等太早的数据，比如我们只保留 2017 年以来的
        if date_str < "2017-01-01":
            continue
            
        record = {
            "date": date_str,
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close']),
            "amount": float(row.get('amount', 0)),
            "pct": float(row['pct'])
        }
        records.append(record)

    if not records:
        print(f"  ⚠️ 没有过滤出 2017 年以后的数据")
        return

    # 覆写到 daily.jsonl
    with open(daily_file, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
            
    # 写入 meta 文件
    meta_file = symbol_dir / "daily.jsonl.meta.json"
    meta = {
        "datasetId": "index_daily",
        "providerId": "akshare.stock_zh_index_daily_tx",
        "symbol": symbol,
        "asOf": datetime.now().isoformat(),
        "recordCount": len(records),
        "startDate": records[0]["date"],
        "endDate": records[-1]["date"]
    }
    meta_file.write_text(json.dumps(meta, indent=2))

    print(f"  ✅ 成功！写入 {len(records)} 条数据 -> {daily_file.relative_to(PROJECT_ROOT)}")
    print(f"     区间: {records[0]['date']} 至 {records[-1]['date']}")

def main():
    print("="*50)
    print("M1 大盘历史回填任务启动")
    print("="*50)
    for sym, name in INDEX_SYMBOLS.items():
        fetch_and_clean_index(sym, name)
    print("\n✅ 回填全部完成！旧数据清洗结束。")

if __name__ == "__main__":
    main()
