#!/usr/bin/env python3
"""
全市场涨跌家数统计

数据源：ak.stock_zh_a_spot()
用途：实时统计A股涨跌家数，前端展示

返回格式：
{
  "ok": true,
  "up": 866,
  "down": 4541,
  "flat": 81,
  "total": 5488,
  "ratio": 0.19,
  "sentiment": "恐慌"
}
"""
import json
import sys


def main() -> int:
    try:
        import akshare as ak
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"import akshare failed: {e}"}), file=sys.stdout)
        return 0

    try:
        # 获取所有A股实时行情
        df = ak.stock_zh_a_spot()

        if df is None or df.empty:
            print(json.dumps({"ok": False, "error": "empty result"}), file=sys.stdout)
            return 0

        # 检查涨跌幅列
        change_col = "涨跌幅"
        if change_col not in df.columns:
            print(json.dumps({"ok": False, "error": f"missing column: {change_col}"}), file=sys.stdout)
            return 0

        # 统计涨跌家数
        up = int(df[df[change_col] > 0].shape[0])
        down = int(df[df[change_col] < 0].shape[0])
        flat = int(df[df[change_col] == 0].shape[0])

        total = up + down + flat
        ratio = round(up / down, 2) if down > 0 else float('inf')

        # 情绪判断
        if ratio < 0.3:
            sentiment = "恐慌"
        elif ratio > 2.0:
            sentiment = "亢奋"
        else:
            sentiment = "正常"

        print(json.dumps({
            "ok": True,
            "up": up,
            "down": down,
            "flat": flat,
            "total": total,
            "ratio": ratio,
            "sentiment": sentiment
        }, ensure_ascii=False), file=sys.stdout)
        return 0

    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}), file=sys.stdout)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
