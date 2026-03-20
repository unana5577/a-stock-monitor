#!/usr/bin/env python3
"""
分钟数据目录整理脚本

功能：
- 将所有分时数据整理到 data/minute/ 目录
- 迁移：runtime/minute/ → data/minute/ (指数分时)
- 迁移：data/volume-*.jsonl → data/minute/ (成交额分时)

用法：
  python3 organize_minute_data.py
"""
import json
import os
import shutil
import sys
from datetime import datetime


def main():
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_dir, "data")
    minute_dir = os.path.join(data_dir, "minute")
    runtime_minute = os.path.join(project_dir, "runtime", "minute")

    # 创建目标目录
    os.makedirs(minute_dir, exist_ok=True)

    migrated = []
    errors = []

    # 1. 迁移 runtime/minute/ -> data/minute/
    if os.path.exists(runtime_minute):
        for filename in os.listdir(runtime_minute):
            if filename.startswith("minute-"):
                src = os.path.join(runtime_minute, filename)
                dst = os.path.join(minute_dir, filename)
                try:
                    shutil.move(src, dst)
                    migrated.append(f"runtime/minute/{filename} -> data/minute/{filename}")
                except Exception as e:
                    errors.append(f"移动 {filename} 失败: {e}")

    # 2. 迁移 data/volume-*.jsonl -> data/minute/
    for filename in os.listdir(data_dir):
        if filename.startswith("volume-") and filename.endswith(".jsonl"):
            src = os.path.join(data_dir, filename)
            dst = os.path.join(minute_dir, filename)
            try:
                shutil.move(src, dst)
                migrated.append(f"data/{filename} -> data/minute/{filename}")
            except Exception as e:
                errors.append(f"移动 {filename} 失败: {e}")

    result = {
        "ok": True,
        "migrated": migrated,
        "errors": errors,
        "message": f"已迁移 {len(migrated)} 个文件"
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
