#!/usr/bin/env python3
"""
涨跌家数持久化脚本

功能：将当天的涨跌家数写入历史记录文件
调用时机：收盘后（11:31 和 15:01）
"""
import json
import os
import sys
from datetime import datetime

def main():
    # 项目根目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    os.chdir(project_dir)

    # 读取当前缓存的涨跌家数
    cache_file = os.path.join(project_dir, 'data', 'breadth-cache.json')

    if not os.path.exists(cache_file):
        print(json.dumps({"ok": False, "error": "breadth-cache.json not found"}))
        return 1

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"read cache failed: {e}"}))
        return 1

    if not data.get('ok'):
        print(json.dumps({"ok": False, "error": "breadth cache not ok"}))
        return 1

    day = datetime.now().strftime("%Y-%m-%d")
    timestamp = int(datetime.now().timestamp() * 1000)

    # 涨跌家数历史文件
    history_file = os.path.join(project_dir, 'data', 'breadth-history.jsonl')

    # 检查是否已存在今天的记录
    existing_days = set()
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line.strip())
                    if isinstance(row, dict) and row.get('date'):
                        existing_days.add(row['date'])
                    elif isinstance(row, list) and len(row) > 1:
                        existing_days.add(row[1])  # 旧格式：日期在第2位
                except:
                    pass

    if day in existing_days:
        print(json.dumps({
            "ok": True,
            "exists": True,
            "day": day,
            "message": "Today's breadth already recorded"
        }))
        return 0

    # 写入历史记录
    # 格式: {"timestamp": xxx, "date": "YYYY-MM-DD", "up": xxx, "down": xxx, "flat": xxx, "total": xxx}
    row = {
        "timestamp": timestamp,
        "date": day,
        "up": data.get('up', 0),
        "down": data.get('down', 0),
        "flat": data.get('flat', 0),
        "total": data.get('total', 0)
    }

    with open(history_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')

    print(json.dumps({
        "ok": True,
        "day": day,
        "up": data.get('up'),
        "down": data.get('down'),
        "flat": data.get('flat'),
        "total": data.get('total'),
        "path": history_file
    }, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
