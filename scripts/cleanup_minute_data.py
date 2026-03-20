#!/usr/bin/env python3
"""
分钟数据清理脚本

功能：
- 保留5个交易日的分钟数据
- 每周清理一次（自然日7天）
- 清理目录：data/minute/

用法：
  python3 cleanup_minute_data.py
"""
import json
import os
import sys
from datetime import datetime, timedelta


def get_trading_days(n=10):
    """获取最近n个交易日（排除周末）"""
    days = []
    today = datetime.now()
    for i in range(1, 30):
        date = today - timedelta(days=i)
        if date.weekday() < 5:
            days.append(date.strftime("%Y%m%d"))
        if len(days) >= n:
            break
    return set(days)


def cleanup_directory(dir_path, keep_days=7, keep_trading_days=5):
    """清理目录中的旧文件"""
    if not os.path.exists(dir_path):
        return {"ok": True, "message": "目录不存在"}

    keep_dates = get_trading_days(n=keep_trading_days)
    cutoff = datetime.now() - timedelta(days=keep_days)
    cutoff_str = cutoff.strftime("%Y%m%d")

    deleted = []
    kept = []

    for filename in os.listdir(dir_path):
        if not filename.startswith("minute-") and not filename.startswith("volume-"):
            continue

        parts = filename.replace(".jsonl", "").split("-")
        if len(parts) < 2:
            continue

        file_date = parts[1]

        keep = file_date >= cutoff_str or file_date in keep_dates

        if keep:
            kept.append(filename)
        else:
            filepath = os.path.join(dir_path, filename)
            try:
                os.remove(filepath)
                deleted.append(filename)
            except Exception as e:
                print(f"删除失败 {filename}: {e}", file=sys.stderr)

    return {
        "ok": True,
        "deleted": len(deleted),
        "kept": len(kept),
        "deleted_files": deleted[:10],
        "message": f"已删除 {len(deleted)} 个文件，保留 {len(kept)} 个文件"
    }


def main():
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    minute_dir = os.path.join(project_dir, "data", "minute")

    keep_days = 7
    keep_trading_days = 5

    if len(sys.argv) > 1:
        try:
            keep_days = int(sys.argv[1])
        except:
            pass
    if len(sys.argv) > 2:
        try:
            keep_trading_days = int(sys.argv[2])
        except:
            pass

    result = cleanup_directory(minute_dir, keep_days, keep_trading_days)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
