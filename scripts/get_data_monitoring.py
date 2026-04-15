#!/usr/bin/env python3
"""
数据流程监控脚本

功能：
1. 判断当前时间状态（休市/午休/收盘/盘中）
2. 检查数据文件状态
3. 检查数据更新频率
4. 返回监控结果JSON
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 时区设置
TZ = timezone(timedelta(hours=8))

def get_current_time():
    """获取当前时间"""
    return datetime.now(TZ)

def is_weekend(date):
    """判断是否是周末"""
    return date.weekday() >= 5  # 5=周六, 6=周日

def is_holiday(date):
    """判断是否是节假日"""
    holiday_file = Path("config/holidays.json")
    if not holiday_file.exists():
        holiday_file = Path("data/holiday.txt")

    if holiday_file.exists():
        try:
            if holiday_file.suffix == '.json':
                with open(holiday_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    holidays = set(data.get('holidays', []))
            else:
                with open(holiday_file, 'r', encoding='utf-8') as f:
                    holidays = set(line.strip() for line in f if line.strip())

            date_str = date.strftime("%Y-%m-%d")
            return date_str in holidays
        except:
            pass
    return False

def is_trading_day(date):
    """判断是否是交易日"""
    return not is_weekend(date) and not is_holiday(date)

def get_time_status():
    """
    获取当前时间状态

    返回:
    {
        "state": "盘中" | "午休" | "收盘后" | "非交易时段" | "休市",
        "emoji": "📈" | "☕" | "🏁" | "🌙" | "📅",
        "description": "描述文本"
    }
    """
    now = get_current_time()
    current_time = now.hour * 60 + now.minute
    current_date = now.date()

    # 判断是否是交易日
    trading_day = is_trading_day(current_date)

    if not trading_day:
        return {
            "state": "休市",
            "emoji": "📅",
            "description": "今日休市",
            "currentTime": now.strftime("%H:%M:%S")
        }

    # 交易日，判断时段
    # 盘前: 09:15-09:30 (555-570)
    if 555 <= current_time < 570:
        return {
            "state": "盘前",
            "emoji": "🌅",
            "description": "盘前时段",
            "currentTime": now.strftime("%H:%M:%S")
        }

    # 上午盘中: 09:30-11:30 (570-690)
    if 570 <= current_time < 690:
        return {
            "state": "盘中",
            "emoji": "📈",
            "description": "上午交易中",
            "currentTime": now.strftime("%H:%M:%S")
        }

    # 午休: 11:30-13:00 (690-780)
    if 690 <= current_time < 780:
        return {
            "state": "午休",
            "emoji": "☕",
            "description": "午休时段",
            "currentTime": now.strftime("%H:%M:%S")
        }

    # 下午盘中: 13:00-15:00 (780-900)
    if 780 <= current_time < 900:
        return {
            "state": "盘中",
            "emoji": "📈",
            "description": "下午交易中",
            "currentTime": now.strftime("%H:%M:%S")
        }

    # 收盘后: 15:00-17:00 (900-1020)
    if 900 <= current_time < 1020:
        return {
            "state": "收盘后",
            "emoji": "🏁",
            "description": "收盘后数据更新中",
            "currentTime": now.strftime("%H:%M:%S")
        }

    # 晚上: 17:00以后
    return {
        "state": "晚间",
        "emoji": "🌙",
        "description": "非交易时段",
        "currentTime": now.strftime("%H:%M:%S")
    }

def get_file_latest_time(file_path):
    """获取文件最后修改时间"""
    if not os.path.exists(file_path):
        return None

    mtime = os.path.getmtime(file_path)
    return datetime.fromtimestamp(mtime, TZ)

def get_jsonl_latest_date(file_path):
    """获取JSONL文件中最新记录的日期"""
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if not lines:
                return None

            last_line = lines[-1].strip()
            if not last_line:
                return None

            record = json.loads(last_line)

            # 尝试获取date字段
            if 'date' in record:
                return record['date']
            if 'time' in record:
                time_str = record['time']
                if isinstance(time_str, str) and len(time_str) >= 10:
                    return time_str[:10]

            return None
    except:
        return None

def check_etf_daily_data():
    """检查ETF日线数据"""
    etf_dir = Path("data/etf_daily")
    etf_codes = ['512400', '512480', '515120', '515880', '516010',
                 '516160', '516510', '562500', '563530']

    results = []
    today = get_current_time().strftime("%Y-%m-%d")

    for code in etf_codes:
        file_path = etf_dir / f"etf_{code}.jsonl"

        if not file_path.exists():
            results.append({
                "code": code,
                "status": "missing",
                "message": "文件不存在"
            })
            continue

        latest_date = get_jsonl_latest_date(str(file_path))

        if not latest_date:
            results.append({
                "code": code,
                "status": "empty",
                "message": "文件为空"
            })
            continue

        if latest_date == today:
            results.append({
                "code": code,
                "status": "ok",
                "latest_date": latest_date,
                "message": f"已更新至{latest_date}"
            })
        else:
            results.append({
                "code": code,
                "status": "delayed",
                "latest_date": latest_date,
                "message": f"数据落后({latest_date})"
            })

    ok_count = sum(1 for r in results if r['status'] == 'ok')
    delayed_count = sum(1 for r in results if r['status'] == 'delayed')
    failed_count = sum(1 for r in results if r['status'] in ['missing', 'empty'])

    return {
        "name": "ETF日线数据",
        "total": len(etf_codes),
        "ok": ok_count,
        "delayed": delayed_count,
        "failed": failed_count,
        "details": results
    }

def check_index_daily_data():
    """检查指数日线数据"""
    index_dir = Path("data/index_daily")
    index_codes = {
        '000001': '上证指数',
        '399001': '深证成指',
        '399006': '创业板指',
        '000688': '科创板指'
    }

    results = []
    today = get_current_time().strftime("%Y-%m-%d")

    for code, name in index_codes.items():
        file_path = index_dir / f"index_{code}.jsonl"

        if not file_path.exists():
            results.append({
                "code": code,
                "name": name,
                "status": "missing",
                "message": "文件不存在"
            })
            continue

        latest_date = get_jsonl_latest_date(str(file_path))

        if not latest_date:
            results.append({
                "code": code,
                "name": name,
                "status": "empty",
                "message": "文件为空"
            })
            continue

        if latest_date == today:
            results.append({
                "code": code,
                "name": name,
                "status": "ok",
                "latest_date": latest_date,
                "message": f"已更新至{latest_date}"
            })
        else:
            results.append({
                "code": code,
                "name": name,
                "status": "delayed",
                "latest_date": latest_date,
                "message": f"数据落后({latest_date})"
            })

    ok_count = sum(1 for r in results if r['status'] == 'ok')
    delayed_count = sum(1 for r in results if r['status'] == 'delayed')
    failed_count = sum(1 for r in results if r['status'] in ['missing', 'empty'])

    return {
        "name": "指数日线数据",
        "total": len(index_codes),
        "ok": ok_count,
        "delayed": delayed_count,
        "failed": failed_count,
        "details": results
    }

def check_minute_data():
    """检查分时数据"""
    today = get_current_time().strftime("%Y%m%d")
    minute_file = Path(f"data/minute-{today}.jsonl")

    if not minute_file.exists():
        return {
            "name": "分时数据",
            "status": "missing",
            "message": "今日分时文件不存在"
        }

    # 检查文件修改时间
    mtime = get_file_latest_time(str(minute_file))
    if not mtime:
        return {
            "name": "分时数据",
            "status": "error",
            "message": "无法获取文件时间"
        }

    # 计算时间差
    now = get_current_time()
    time_diff = (now - mtime).total_seconds() / 60  # 分钟

    time_status = get_time_status()

    # 只有在盘中时才检查更新频率
    if time_status['state'] == '盘中':
        if time_diff > 5:
            return {
                "name": "分时数据",
                "status": "stale",
                "last_update": mtime.strftime("%H:%M:%S"),
                "minutes_ago": int(time_diff),
                "message": f"数据已{int(time_diff)}分钟未更新"
            }
        else:
            return {
                "name": "分时数据",
                "status": "ok",
                "last_update": mtime.strftime("%H:%M:%S"),
                "minutes_ago": int(time_diff),
                "message": f"{int(time_diff)}分钟前更新"
            }
    else:
        return {
            "name": "分时数据",
            "status": "ok",
            "last_update": mtime.strftime("%H:%M:%S"),
            "message": "非交易时段"
        }

def check_market_snapshot():
    """检查市场快照数据"""
    breadth_file = Path("data/market/breadth-cache.json")

    if not breadth_file.exists():
        return {
            "name": "市场快照",
            "status": "missing",
            "message": "快照文件不存在"
        }

    mtime = get_file_latest_time(str(breadth_file))
    if not mtime:
        return {
            "name": "市场快照",
            "status": "error",
            "message": "无法获取文件时间"
        }

    now = get_current_time()
    time_diff = (now - mtime).total_seconds() / 60  # 分钟

    time_status = get_time_status()

    # 只有在盘中时才检查更新频率
    if time_status['state'] == '盘中':
        if time_diff > 8:
            return {
                "name": "市场快照",
                "status": "stale",
                "last_update": mtime.strftime("%H:%M:%S"),
                "minutes_ago": int(time_diff),
                "message": f"已{int(time_diff)}分钟未更新"
            }
        else:
            return {
                "name": "市场快照",
                "status": "ok",
                "last_update": mtime.strftime("%H:%M:%S"),
                "minutes_ago": int(time_diff),
                "message": f"{int(time_diff)}分钟前更新"
            }
    else:
        return {
            "name": "市场快照",
            "status": "ok",
            "last_update": mtime.strftime("%H:%M:%S"),
            "message": "非交易时段"
        }

def check_warmup_data():
    """检查Warmup缓存"""
    warmup_file = Path("data/sector-history-warmup-60.json")

    if not warmup_file.exists():
        return {
            "name": "Warmup缓存",
            "status": "missing",
            "message": "文件不存在"
        }

    try:
        with open(warmup_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data or 'history' not in data:
            return {
                "name": "Warmup缓存",
                "status": "error",
                "message": "文件格式错误"
            }

        # 检查第一个板块的最新日期
        history = data['history']
        first_sector = list(history.keys())[0] if history else None

        if not first_sector or not history[first_sector]:
            return {
                "name": "Warmup缓存",
                "status": "empty",
                "message": "无数据"
            }

        latest_record = history[first_sector][-1]
        latest_date = latest_record.get('date')

        if not latest_date:
            return {
                "name": "Warmup缓存",
                "status": "error",
                "message": "日期字段缺失"
            }

        today = get_current_time().strftime("%Y-%m-%d")

        if latest_date == today:
            return {
                "name": "Warmup缓存",
                "status": "ok",
                "latest_date": latest_date,
                "record_count": len(history[first_sector]),
                "message": f"已更新至{latest_date}"
            }
        else:
            return {
                "name": "Warmup缓存",
                "status": "delayed",
                "latest_date": latest_date,
                "record_count": len(history[first_sector]),
                "message": f"数据落后({latest_date})"
            }
    except Exception as e:
        return {
            "name": "Warmup缓存",
            "status": "error",
            "message": f"读取失败: {str(e)}"
        }

def check_lifecycle_data():
    """检查Lifecycle数据"""
    lifecycle_file = Path("data/sector-lifecycle.json")

    if not lifecycle_file.exists():
        return {
            "name": "Lifecycle",
            "status": "missing",
            "message": "文件不存在"
        }

    try:
        with open(lifecycle_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not data or 'day' not in data:
            return {
                "name": "Lifecycle",
                "status": "error",
                "message": "文件格式错误"
            }

        latest_date = data['day']
        items_count = len(data.get('items', []))

        if not latest_date:
            return {
                "name": "Lifecycle",
                "status": "error",
                "message": "日期字段缺失"
            }

        today = get_current_time().strftime("%Y-%m-%d")

        if latest_date == today:
            return {
                "name": "Lifecycle",
                "status": "ok",
                "latest_date": latest_date,
                "items_count": items_count,
                "message": f"已更新至{latest_date}"
            }
        else:
            return {
                "name": "Lifecycle",
                "status": "delayed",
                "latest_date": latest_date,
                "items_count": items_count,
                "message": f"数据落后({latest_date})"
            }
    except Exception as e:
        return {
            "name": "Lifecycle",
            "status": "error",
            "message": f"读取失败: {str(e)}"
        }

def collect_alerts(data_sources):
    """收集异常警告"""
    alerts = []

    for source_name, source_data in data_sources.items():
        status = source_data.get('status')

        if status == 'missing':
            alerts.append({
                "level": "error",
                "source": source_name,
                "message": f"{source_data['name']}文件缺失"
            })
        elif status == 'stale':
            alerts.append({
                "level": "warning",
                "source": source_name,
                "message": f"{source_data['name']}已{source_data.get('minutes_ago', 0)}分钟未更新"
            })
        elif status == 'error':
            alerts.append({
                "level": "error",
                "source": source_name,
                "message": source_data.get('message', '未知错误')
            })

        # 检查日线数据的失败项
        if 'failed' in source_data and source_data['failed'] > 0:
            alerts.append({
                "level": "error",
                "source": source_name,
                "message": f"{source_data['failed']}个数据源失败"
            })

        # 检查日线数据的延迟项
        if 'delayed' in source_data and source_data['delayed'] > 0:
            alerts.append({
                "level": "warning",
                "source": source_name,
                "message": f"{source_data['delayed']}个数据源落后"
            })

    return alerts

def main():
    """主函数"""
    now = get_current_time()

    # 获取时间状态
    time_status = get_time_status()

    # 检查各数据源
    data_sources = {
        "etf_daily": check_etf_daily_data(),
        "index_daily": check_index_daily_data(),
        "minute": check_minute_data(),
        "market_snapshot": check_market_snapshot(),
        "warmup": check_warmup_data(),
        "lifecycle": check_lifecycle_data()
    }

    # 收集异常
    alerts = collect_alerts(data_sources)

    # 构建结果
    result = {
        "timestamp": now.isoformat(),
        "currentTime": now.strftime("%H:%M:%S"),
        "timeStatus": time_status,
        "dataSources": data_sources,
        "alerts": alerts,
        "summary": {
            "total_sources": len(data_sources),
            "healthy_sources": sum(1 for s in data_sources.values() if s.get('status') == 'ok'),
            "warning_sources": sum(1 for s in data_sources.values() if s.get('status') in ['delayed', 'stale']),
            "error_sources": sum(1 for s in data_sources.values() if s.get('status') in ['missing', 'error', 'empty'])
        }
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
