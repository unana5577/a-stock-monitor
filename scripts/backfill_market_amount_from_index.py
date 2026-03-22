#!/usr/bin/env python3
"""
市场日线成交额补齐脚本

从本地指数日线数据（上证+深证）的amount字段补齐market-amount-daily.jsonl
"""
import json
import os
import sys
from datetime import datetime


def main() -> int:
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_dir, "data")
    index_dir = os.path.join(data_dir, "index_daily")
    out_file = os.path.join(data_dir, "market", "market-amount-daily.jsonl")

    # 读取现有数据，获取已存在的日期
    existing_dates = set()
    if os.path.exists(out_file):
        with open(out_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line.strip())
                    if row.get('date'):
                        existing_dates.add(row['date'])
                except:
                    pass

    # 读取指数数据
    sh_file = os.path.join(index_dir, "index_000001.jsonl")
    sz_file = os.path.join(index_dir, "index_399001.jsonl")

    sh_data = {}
    sz_data = {}

    if os.path.exists(sh_file):
        with open(sh_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line.strip())
                    date = row.get('date')
                    amount = row.get('amount')
                    if date and amount and amount > 0:
                        sh_data[date] = float(amount)
                except:
                    pass

    if os.path.exists(sz_file):
        with open(sz_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line.strip())
                    date = row.get('date')
                    amount = row.get('amount')
                    if date and amount and amount > 0:
                        sz_data[date] = float(amount)
                except:
                    pass

    # 合并数据
    all_dates = set(sh_data.keys()) | set(sz_data.keys())
    new_rows = []
    updated = 0

    for date in sorted(all_dates):
        if date in existing_dates:
            continue
        sh_amt = sh_data.get(date, 0)
        sz_amt = sz_data.get(date, 0)
        total = sh_amt + sz_amt
        if total > 0:
            new_rows.append({
                "date": date,
                "total": total,
                "sh": sh_amt,
                "sz": sz_amt
            })
            updated += 1

    # 追加写入
    if new_rows:
        with open(out_file, 'a', encoding='utf-8') as f:
            for row in new_rows:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')

    result = {
        "ok": True,
        "updated": updated,
        "existing": len(existing_dates),
        "total": len(existing_dates) + updated,
        "unit": "yuan",
        "source": "index_daily"
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
