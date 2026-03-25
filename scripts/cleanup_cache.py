#!/usr/bin/env python3
"""
Cleanup Agent 数据缓存清理工具

功能：
1. 扫描 data/ 目录下的所有缓存文件
2. 检查缓存的数据日期是否与期望日期一致（考虑交易日）
3. 清理过期的缓存文件
4. 生成清理报告

使用：
  python scripts/cleanup_cache.py scan          # 只扫描，不删除
  python scripts/cleanup_cache.py clean          # 扫描 + 删除过期缓存
  python scripts/cleanup_cache.py check <类型>  # 检查特定类型缓存
"""

import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

# 缓存类型定义
CACHE_TYPES = {
    "sector-lifecycle": {
        "pattern": "sector-lifecycle-*.json",
        "day_field": "day",
        "desc": "板块生命周期缓存",
        "can_delete": True  # 可以直接删除
    },
    "intraday-rotation": {
        "pattern": "intraday-rotation-*.json",
        "day_field": "day",
        "desc": "盘中轮动缓存",
        "can_delete": True
    },
    "sector-analysis-ai": {
        "pattern": "sector-analysis-ai-*.json",
        "day_field": "date",
        "desc": "AI分析缓存",
        "can_delete": True
    }
}

# warmup 是预热数据文件，不能删除，只能通知重新生成
WARMUP_FILE = {
    "sector-history-warmup-60.json": {
        "desc": "板块预热数据（每日15:30生成）",
        "action": "notify_data_agent"  # 过期时通知 Data Agent 重新生成
    }
}

# 允许的最大交易日差距（超过这个差距才算过期）
MAX_TRADING_DAY_GAP = 3
# 保留最近N个交易日的缓存
KEEP_RECENT_DAYS = 5


def log(msg, emoji="📋"):
    """统一日志输出"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{emoji} [{ts}] {msg}")


def load_holidays():
    """加载节假日配置"""
    holidays_file = ROOT / "config" / "holidays.json"
    if not holidays_file.exists():
        return set()

    try:
        with open(holidays_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(data.get('holidays', []))
    except:
        return set()


def is_trading_day(date):
    """判断是否为交易日（排除周末和节假日）"""
    # 周末排除
    if date.weekday() >= 5:
        return False

    # 节假日排除
    date_str = date.strftime('%Y-%m-%d')
    holidays = load_holidays()
    if date_str in holidays:
        return False

    return True


def get_nth_trading_day_before(date, n):
    """获取 date 之前第 n 个交易日"""
    d = date - timedelta(days=1)  # 从前一天开始
    count = 0

    while count < n:
        if is_trading_day(d):
            count += 1
            if count >= n:
                return d
        d = d - timedelta(days=1)

    return d


def get_expected_trading_day():
    """获取期望的数据日期（最近的交易日）"""
    now = datetime.now()
    hour = now.hour

    # 盘后期望今天（如果是交易日），盘前期望T-1
    if hour >= 15:
        if is_trading_day(now):
            return now
        else:
            return get_nth_trading_day_before(now, 1)
    else:
        return get_nth_trading_day_before(now, 1)


def parse_date_from_filename(filename):
    """从文件名中解析日期（如 sector-lifecycle-60-xxx-20260323.json -> 2026-03-23）"""
    match = re.search(r'(\d{4})(\d{2})(\d{2})\.json$', filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None


def get_cache_data_date(filepath, cache_type):
    """获取缓存中的实际数据日期"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        day_field = CACHE_TYPES[cache_type]["day_field"]
        day = data.get(day_field)

        # 对于 sector-history，需要从 history 里取实际最新日期
        if cache_type == "sector-history":
            history = data.get("history", {})
            dates = []
            for name, arr in history.items():
                if isinstance(arr, list) and arr:
                    d = arr[-1].get("date")
                    if d:
                        dates.append(d)
            if dates:
                return max(dates)  # 返回实际最新日期
            return day  # fallback

        return day
    except Exception as e:
        return None


def count_trading_days_between(start_date, end_date):
    """计算两个日期之间的交易日天数"""
    if not start_date or not end_date:
        return 0

    start = datetime.strptime(str(start_date), '%Y-%m-%d')
    end = datetime.strptime(str(end_date), '%Y-%m-%d')

    if start > end:
        start, end = end, start

    count = 0
    d = start + timedelta(days=1)  # 不包括start当天
    while d <= end:
        if is_trading_day(d):
            count += 1
        d = d + timedelta(days=1)

    return count


def check_cache_file(filepath, cache_type):
    """检查单个缓存文件是否过期"""
    try:
        filename = os.path.basename(filepath)
        cache_day = get_cache_data_date(filepath, cache_type)
        expected_day = get_expected_trading_day()
        expected_str = expected_day.strftime('%Y-%m-%d')

        if not cache_day:
            return {
                "file": filepath,
                "status": "no_date",
                "cache_day": None,
                "expected": expected_str,
                "stale": True,
                "reason": "缓存无日期字段"
            }

        # 计算交易日差距
        trading_day_gap = count_trading_days_between(cache_day, expected_str)

        if trading_day_gap <= MAX_TRADING_DAY_GAP:
            return {
                "file": filepath,
                "status": "fresh",
                "cache_day": cache_day,
                "expected": expected_str,
                "stale": False,
                "gap": trading_day_gap
            }
        else:
            return {
                "file": filepath,
                "status": "stale",
                "cache_day": cache_day,
                "expected": expected_str,
                "stale": True,
                "gap": trading_day_gap,
                "reason": f"落后{trading_day_gap}个交易日"
            }

    except Exception as e:
        return {
            "file": filepath,
            "status": "error",
            "cache_day": None,
            "expected": None,
            "stale": True,
            "error": str(e)
        }


def scan_cache_type(cache_type):
    """扫描特定类型的缓存"""
    cache_info = CACHE_TYPES[cache_type]
    pattern = cache_info["pattern"]
    desc = cache_info["desc"]

    log(f"\n扫描 {desc}...", "🔍")

    files = glob.glob(str(DATA_DIR / pattern))
    if not files:
        log(f"  没有找到文件", "⚠️")
        return []

    results = []

    for filepath in files:
        result = check_cache_file(filepath, cache_type)
        results.append(result)

        filename = os.path.basename(filepath)
        if result["status"] == "fresh":
            log(f"  ✅ {filename} (数据={result['cache_day']}, 差距={result.get('gap', 0)}日)", "")
        elif result["status"] == "stale":
            reason = result.get("reason", "")
            log(f"  ❌ {filename} (数据={result['cache_day']}, {reason})", "")
        elif result["status"] == "no_date":
            log(f"  ⚠️ {filename} (无日期字段)", "")
        else:
            log(f"  ⚠️ {filename} (解析错误)", "")

    return results


def scan_warmup():
    """检查 warmup 文件（预热数据）"""
    log(f"\n扫描预热数据文件...", "🔍")

    results = []
    expected_day = get_expected_trading_day()
    expected_str = expected_day.strftime('%Y-%m-%d')

    for filename, info in WARMUP_FILE.items():
        filepath = DATA_DIR / filename
        if not filepath.exists():
            log(f"  ⚠️ {filename} 不存在，需要 Data Agent 生成", "")
            results.append({
                "file": str(filepath),
                "status": "missing",
                "cache_day": None,
                "expected": expected_str,
                "stale": True,
                "reason": "文件不存在",
                "action": "generate"
            })
            continue

        cache_day = get_cache_data_date(str(filepath), "sector-history")
        trading_day_gap = count_trading_days_between(cache_day, expected_str)

        if trading_day_gap <= MAX_TRADING_DAY_GAP:
            log(f"  ✅ {filename} (数据={cache_day}, 差距={trading_day_gap}日)", "")
            results.append({
                "file": str(filepath),
                "status": "fresh",
                "cache_day": cache_day,
                "expected": expected_str,
                "stale": False,
                "gap": trading_day_gap
            })
        else:
            log(f"  ❌ {filename} (数据={cache_day}, 落后{trading_day_gap}日, 需要重新生成)", "")
            results.append({
                "file": str(filepath),
                "status": "stale",
                "cache_day": cache_day,
                "expected": expected_str,
                "stale": True,
                "gap": trading_day_gap,
                "reason": f"落后{trading_day_gap}个交易日",
                "action": "generate"
            })

    return results


def scan_all():
    """扫描所有缓存和预热数据"""
    print("\n" + "=" * 60)
    print("🔍 Cleanup Agent - 缓存扫描")
    print("=" * 60)

    expected_day = get_expected_trading_day()
    print(f"\n期望数据日期: {expected_day.strftime('%Y-%m-%d')}")
    print(f"今天: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"允许最大差距: {MAX_TRADING_DAY_GAP} 个交易日")
    print()

    all_results = []
    stale_files = []
    fresh_count = 0
    warmup_issues = []

    # 1. 扫描预热数据文件
    log("📦 预热数据文件", "")
    warmup_results = scan_warmup()
    all_results.extend(warmup_results)
    for r in warmup_results:
        if r["status"] == "fresh":
            fresh_count += 1
        elif r["status"] in ("stale", "missing"):
            warmup_issues.append(r)

    # 2. 扫描缓存文件
    log("\n📦 缓存文件", "")
    for cache_type in CACHE_TYPES:
        results = scan_cache_type(cache_type)
        all_results.extend(results)

        for r in results:
            if r["status"] == "stale":
                stale_files.append(r)
            elif r["status"] == "fresh":
                fresh_count += 1

    # 汇总
    print("\n" + "=" * 60)
    print("📊 扫描汇总")
    print("=" * 60)
    print(f"  正常: {fresh_count} 个")
    print(f"  过期缓存: {len(stale_files)} 个")
    print(f"  预热数据问题: {len(warmup_issues)} 个")

    if warmup_issues:
        print(f"\n⚠️  预热数据需要 Data Agent 处理:")
        for r in warmup_issues:
            print(f"  - {os.path.basename(r['file'])}: {r.get('reason', '')}")

    if stale_files:
        print(f"\n⚠️  建议清理 {len(stale_files)} 个过期缓存:")
        for r in stale_files[:10]:
            print(f"  - {os.path.basename(r['file'])} ({r.get('reason', '')})")
        if len(stale_files) > 10:
            print(f"  ... 还有 {len(stale_files) - 10} 个")

    print("=" * 60)
    return stale_files, warmup_issues


def should_delete(filepath, cache_day):
    """判断是否应该删除缓存（超过保留天数才删除）"""
    if not cache_day:
        return True  # 无日期的直接删除

    expected_day = get_expected_trading_day()
    trading_day_gap = count_trading_days_between(cache_day, expected_day.strftime('%Y-%m-%d'))

    # 超过保留天数才删除
    return trading_day_gap > KEEP_RECENT_DAYS


def clean_cache(results):
    """清理过期缓存"""
    if not results:
        log("没有需要清理的缓存", "✅")
        return []

    print("\n" + "=" * 60)
    print("🗑️  Cleanup Agent - 清理过期缓存")
    print("=" * 60)
    print(f"保留最近 {KEEP_RECENT_DAYS} 个交易日的缓存")

    deleted = []
    skipped = []

    for r in results:
        cache_day = r.get("cache_day")
        # 检查是否超过保留天数
        if not should_delete(r["file"], cache_day):
            log(f"跳过(保留期): {os.path.basename(r['file'])} (数据={cache_day})", "⏭️")
            skipped.append(r)
            continue

        try:
            os.remove(r["file"])
            log(f"删除: {os.path.basename(r['file'])} (数据={cache_day})", "🗑️")
            deleted.append(r["file"])
        except Exception as e:
            log(f"删除失败: {os.path.basename(r['file'])} - {e}", "❌")

    print(f"\n✅ 已删除 {len(deleted)} 个过期缓存")
    if skipped:
        print(f"⏭️  跳过 {len(skipped)} 个（保留期内）")
    print("=" * 60)
    return deleted


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "scan":
        scan_all()
    elif cmd == "clean":
        stale_files, warmup_issues = scan_all()
        if warmup_issues:
            print("\n⚠️  预热数据有问题，需要 Data Agent 处理，不能删除")
        if stale_files:
            print("\n是否删除这些过期缓存？(y/N)")
            response = input().strip().lower()
            if response == 'y':
                clean_cache(stale_files)
            else:
                log("取消清理", "ℹ️")
        else:
            log("没有过期缓存需要清理", "✅")
    elif cmd == "check":
        if len(sys.argv) < 3:
            log("请指定缓存类型", "❌")
            log(f"支持的类型: {', '.join(CACHE_TYPES.keys())}", "ℹ️")
            sys.exit(1)
        cache_type = sys.argv[2]
        if cache_type not in CACHE_TYPES:
            log(f"未知的缓存类型: {cache_type}", "❌")
            sys.exit(1)
        results = scan_cache_type(cache_type)
        stale = [r for r in results if r["stale"]]
        if stale:
            log(f"\n发现 {len(stale)} 个过期缓存", "⚠️")
        else:
            log(f"\n✅ 没有过期缓存", "✅")
    else:
        log(f"未知命令: {cmd}", "❌")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
