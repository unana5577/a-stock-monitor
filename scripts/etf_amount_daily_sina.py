#!/usr/bin/env python3
"""
ETF每日成交额统计

数据源：ak.fund_etf_category_sina(symbol="ETF基金")
用途：记录每天ETF总成交额，供agent分析使用

存储文件：data/etf-amount-daily.jsonl
格式：["YYYY-MM-DD", total_amount, count]
单位：元
"""
import json
import os
import sys
from datetime import datetime


def main() -> int:
    day_override = sys.argv[1] if len(sys.argv) >= 2 else None

    try:
        import akshare as ak
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"import akshare failed: {e}"}), file=sys.stdout)
        return 0

    try:
        # 获取ETF数据
        df = ak.fund_etf_category_sina(symbol="ETF基金")
        if df is None or df.empty:
            print(json.dumps({"ok": False, "error": "empty result"}), file=sys.stdout)
            return 0

        # 检查成交额列
        amount_col = "成交额"
        if amount_col not in df.columns:
            print(json.dumps({"ok": False, "error": f"missing column: {amount_col}"}), file=sys.stdout)
            return 0

        # 计算总成交额
        total = float(df[amount_col].fillna(0).astype(float).sum())
        count = int(df.shape[0])

        # 日期
        day = day_override or datetime.now().strftime("%Y-%m-%d")

        # 存储文件路径
        out_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "data",
            "market",
            "etf-amount-daily.jsonl"
        )
        out_path = os.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        # 读取现有数据，避免重复
        existing_days = set()
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line.strip())
                        if row and len(row) > 0:
                            existing_days.add(row[0])
                    except:
                        pass

        # 如果当天已存在，跳过
        if day in existing_days:
            print(json.dumps({
                "ok": True,
                "exists": True,
                "day": day,
                "message": "Data already exists for this day"
            }, ensure_ascii=False), file=sys.stdout)
            return 0

        # 追加写入文件
        with open(out_path, "a", encoding="utf-8") as f:
            row = {"date": day, "amount": total, "count": count}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

        print(json.dumps({
            "ok": True,
            "day": day,
            "total_amount": total,
            "total_yi": total / 100000000,
            "count": count,
            "path": out_path
        }, ensure_ascii=False), file=sys.stdout)
        return 0

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stdout)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
