#!/usr/bin/env python3
"""
数据健康检查脚本
检查ETF、指数、warmup缓存、lifecycle数据的健康状态
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# 项目根目录
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"

# ETF板块代码
ETF_CODES = ['512400', '512480', '515120', '515880', '516010',
             '516160', '516510', '562500', '563530']

# 指数代码
INDEX_CODES = ['000001', '399001', '399006', '000688']
INDEX_NAMES = {
    '000001': '上证指数',
    '399001': '深证成指',
    '399006': '创业板指',
    '000688': '科创板指'
}

def get_today():
    """获取今天的日期（YYYY-MM-DD格式）"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')

def check_etf_data():
    """检查ETF数据状态"""
    etf_dir = DATA_DIR / "etf_daily"
    status = {
        "total": len(ETF_CODES),
        "ok": 0,
        "delayed": 0,
        "failed": 0,
        "details": []
    }

    today = get_today()

    for code in ETF_CODES:
        file_path = etf_dir / f"etf_{code}.jsonl"

        if not file_path.exists():
            status["failed"] += 1
            status["details"].append({
                "code": code,
                "status": "missing"
            })
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines:
                status["failed"] += 1
                status["details"].append({
                    "code": code,
                    "status": "empty"
                })
                continue

            # 读取最后一条记录
            last_record = json.loads(lines[-1].strip())
            last_date = last_record.get("date", "")

            if last_date < today:
                status["delayed"] += 1
                status["details"].append({
                    "code": code,
                    "status": "delayed",
                    "lastDate": last_date
                })
            else:
                status["ok"] += 1
                status["details"].append({
                    "code": code,
                    "status": "ok",
                    "lastDate": last_date
                })
        except Exception as e:
            status["failed"] += 1
            status["details"].append({
                "code": code,
                "status": "error",
                "error": str(e)
            })

    return status

def check_index_data():
    """检查指数数据状态"""
    index_dir = DATA_DIR / "index_daily"
    status = {
        "total": len(INDEX_CODES),
        "ok": 0,
        "delayed": 0,
        "failed": 0,
        "details": []
    }

    today = get_today()

    for code in INDEX_CODES:
        file_path = index_dir / f"index_{code}.jsonl"
        name = INDEX_NAMES[code]

        if not file_path.exists():
            status["failed"] += 1
            status["details"].append({
                "name": name,
                "code": code,
                "status": "missing"
            })
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines:
                status["failed"] += 1
                status["details"].append({
                    "name": name,
                    "code": code,
                    "status": "empty"
                })
                continue

            last_record = json.loads(lines[-1].strip())
            last_date = last_record.get("date", "")

            if last_date < today:
                status["delayed"] += 1
                status["details"].append({
                    "name": name,
                    "code": code,
                    "status": "delayed",
                    "lastDate": last_date
                })
            else:
                status["ok"] += 1
                status["details"].append({
                    "name": name,
                    "code": code,
                    "status": "ok",
                    "lastDate": last_date
                })
        except Exception as e:
            status["failed"] += 1
            status["details"].append({
                "name": name,
                "code": code,
                "status": "error",
                "error": str(e)
            })

    return status

def check_warmup_data():
    """检查warmup缓存状态"""
    warmup_file = DATA_DIR / "sector-history-warmup-60.json"
    status = {
        "exists": False,
        "latestDate": None,
        "recordCount": 0,
        "status": "unknown"
    }

    if not warmup_file.exists():
        status["status"] = "missing"
        return status

    try:
        with open(warmup_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        status["exists"] = True
        history = data.get("history", {})

        # 检查第一个板块的数据
        first_sector = next(iter(history.keys()), None)
        if first_sector and history[first_sector]:
            records = history[first_sector]
            if records:
                last_record = records[-1]
                status["latestDate"] = last_record.get("date")
                status["recordCount"] = len(records)

                today = get_today()
                if status["latestDate"] == today:
                    status["status"] = "ok"
                elif status["latestDate"] < today:
                    status["status"] = "stale"
                else:
                    status["status"] = "future"
    except Exception as e:
        status["status"] = "error"
        status["error"] = str(e)

    return status

def check_lifecycle_data():
    """检查lifecycle数据状态"""
    lifecycle_file = DATA_DIR / "sector-lifecycle.json"
    status = {
        "exists": False,
        "latestDate": None,
        "itemsCount": 0,
        "status": "unknown"
    }

    if not lifecycle_file.exists():
        status["status"] = "missing"
        return status

    try:
        with open(lifecycle_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        status["exists"] = True
        status["latestDate"] = data.get("day")
        status["itemsCount"] = len(data.get("items", []))

        today = get_today()
        if status["latestDate"] == today:
            status["status"] = "ok"
        elif status["latestDate"] < today:
            status["status"] = "stale"
        else:
            status["status"] = "future"
    except Exception as e:
        status["status"] = "error"
        status["error"] = str(e)

    return status

def calculate_health(etf_status, index_status, warmup_status, lifecycle_status):
    """计算整体健康度"""
    total_checks = 0
    passed_checks = 0

    # ETF检查
    total_checks += etf_status["total"]
    passed_checks += etf_status["ok"]

    # 指数检查
    total_checks += index_status["total"]
    passed_checks += index_status["ok"]

    # Warmup检查
    total_checks += 1
    if warmup_status["status"] == "ok":
        passed_checks += 1

    # Lifecycle检查
    total_checks += 1
    if lifecycle_status["status"] == "ok":
        passed_checks += 1

    # 计算健康度
    if total_checks == 0:
        pass_rate = 0
    else:
        pass_rate = passed_checks / total_checks

    if pass_rate >= 0.9:
        health = "healthy"
    elif pass_rate >= 0.7:
        health = "degraded"
    else:
        health = "critical"

    return {
        "health": health,
        "summary": {
            "total": total_checks,
            "passed": passed_checks,
            "failed": total_checks - passed_checks,
            "passRate": f"{pass_rate * 100:.1f}%"
        }
    }

def main():
    """主函数"""
    timestamp = datetime.now(timezone.utc).isoformat()

    # 检查各数据源
    etf_status = check_etf_data()
    index_status = check_index_data()
    warmup_status = check_warmup_data()
    lifecycle_status = check_lifecycle_data()

    # 计算整体健康度
    health_info = calculate_health(etf_status, index_status, warmup_status, lifecycle_status)

    # 构建结果
    result = {
        "timestamp": timestamp,
        "health": health_info["health"],
        "sources": {
            "etf": etf_status,
            "index": index_status,
            "warmup": warmup_status,
            "lifecycle": lifecycle_status
        },
        "summary": health_info["summary"]
    }

    # 输出JSON
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
