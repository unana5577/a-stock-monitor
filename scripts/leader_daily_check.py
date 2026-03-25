#!/usr/bin/env python3
"""
Leader 工作流工具 - 每日数据质量检查

功能：
1. 检查 warmup 文件是否最新（09:15 / 15:30）
2. 检查前端 lifecycle 接口返回
3. 判断是否需要触发 Data Agent 修复
4. 验证修复后前端正常

使用：
  python scripts/leader_daily_check.py check     # 只检查，不修复
  python scripts/leader_daily_check.py full      # 检查 + 触发修复 + 验证
  python scripts/leader_daily_check.py watch     # 持续监控（每分钟检查）
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(ROOT))


def log(msg, emoji="📋"):
    """统一日志输出"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{emoji} [{ts}] {msg}")


def get_expected_latest_date():
    """根据当前时间获取期望的最新数据日期
    15:00后 → 今天；盘中 → T-1
    """
    now = datetime.now()
    hour = now.hour

    if hour >= 15:
        # 盘后，期望今天
        return now.strftime("%Y-%m-%d")
    else:
        # 盘中，期望T-1
        days_back = 1
        while days_back <= 7:
            check = now - timedelta(days=days_back)
            if check.weekday() < 5:
                return check.strftime("%Y-%m-%d")
            days_back += 1
        return now.strftime("%Y-%m-%d")


def is_trading_time():
    """判断当前是否在交易时间内"""
    now = datetime.now()
    hour, minute = now.hour, now.minute

    # 早盘: 09:30-11:30
    if 9 < hour < 11:
        return True
    if hour == 9 and minute >= 30:
        return True
    if hour == 11 and minute <= 30:
        return True
    # 午盘: 13:00-15:00
    if 13 <= hour < 15:
        return True
    return False


def check_warmup_date():
    """检查 warmup 文件日期"""
    log("检查 warmup 文件日期...", "🔍")

    warmup_file = DATA_DIR / "sector-history-warmup-60.json"
    if not warmup_file.exists():
        log("warmup 文件不存在", "❌")
        return False, "not_found"

    # 文件修改时间
    mtime = datetime.fromtimestamp(warmup_file.stat().st_mtime)
    expected_day = get_expected_latest_date()

    # 读取文件内容获取数据日期
    try:
        with open(warmup_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            history = data.get("history", {})
            latest_dates = []
            for name, arr in history.items():
                if isinstance(arr, list) and len(arr) > 0:
                    latest_dates.append(arr[-1].get("date", ""))
            if latest_dates:
                file_date = max(latest_dates)
                log(f"warmup 数据日期: {file_date}, 期望: {expected_day}", "📊")
                if file_date == expected_day:
                    log("warmup 日期最新", "✅")
                    return True, ""
                else:
                    log(f"warmup 日期过期: {file_date} < {expected_day}", "❌")
                    return False, f"stale_{file_date}"
    except Exception as e:
        log(f"warmup 读取失败: {e}", "❌")
        return False, f"read_error"

    return False, "unknown"


def check_lifecycle_api():
    """检查 lifecycle 接口返回"""
    log("检查 lifecycle 接口...", "🔍")

    try:
        import urllib.request
        url = "http://127.0.0.1:8787/api/sector/lifecycle?days=60"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])
            day = data.get("day", "")
            reason = data.get("reason", "")

            log(f"lifecycle: day={day}, items={len(items)}", "📊")

            if len(items) == 0:
                log("问题: lifecycle 返回空数据", "❌")
                return False, reason or "empty"
            else:
                log("lifecycle 接口正常", "✅")
                return True, ""

    except Exception as e:
        log(f"lifecycle 请求失败: {e}", "❌")
        return False, f"request_error"


def check_history_api():
    """检查 history 接口"""
    log("检查 history 接口...", "🔍")

    try:
        import urllib.request
        url = "http://127.0.0.1:8787/api/sector/history?days=60"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            history = data.get("history", {})
            watch = data.get("watch", [])

            log(f"history: watch={len(watch)}, sectors={len(history)}", "📊")

            if not history or not watch:
                log("问题: history 返回空数据", "❌")
                return False, "empty"
            else:
                log("history 接口正常", "✅")
                return True, ""

    except Exception as e:
        log(f"history 请求失败: {e}", "❌")
        return False, f"request_error"


def trigger_data_agent():
    """触发 Data Agent 修复"""
    log("触发 Data Agent 修复...", "📞")

    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "diagnose_sector_api.py"), "fix"],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            log("Data Agent 修复完成", "✅")
            return True
        else:
            log(f"Data Agent 修复失败: {result.stderr}", "❌")
            return False
    except Exception as e:
        log(f"调用 Data Agent 失败: {e}", "❌")
        return False


def verify_after_fix():
    """修复后验证"""
    log("验证修复结果...", "🔍")

    time.sleep(2)  # 等待数据更新

    lifecycle_ok, _ = check_lifecycle_api()
    if not lifecycle_ok:
        log("修复后 lifecycle 仍为空", "❌")
        return False

    warmup_ok, _ = check_warmup_date()
    if not warmup_ok:
        log("修复后 warmup 仍过期", "❌")
        return False

    log("修复验证通过", "✅")
    return True


def daily_check():
    """每日检查流程"""
    print("\n" + "=" * 60)
    print("📊 Leader 每日检查")
    print("=" * 60 + "\n")

    # 1. 检查 warmup
    warmup_ok, warmup_reason = check_warmup_date()
    print()

    # 2. 检查 lifecycle
    lifecycle_ok, lifecycle_reason = check_lifecycle_api()
    print()

    # 汇总
    print("=" * 60)
    print("📊 检查汇总")
    print("=" * 60)
    print(f"  warmup 文件: {'✅ 最新' if warmup_ok else '❌ 过期/不存在'}")
    print(f"  lifecycle:   {'✅ 正常' if lifecycle_ok else '❌ 空数据/请求失败'}")
    print("=" * 60)

    needs_fix = not warmup_ok or not lifecycle_ok

    if needs_fix:
        print("\n⚠️  发现问题，建议执行 full 命令触发 Data Agent")
        return False
    else:
        print("\n✅ 所有检查��过")
        return True


def full_workflow():
    """完整工作流：检查 + 修复 + 验证"""
    print("\n" + "=" * 60)
    print("📊 Leader 完整工作流（检查 + 修复 + 验证）")
    print("=" * 60 + "\n")

    # 1. 检查
    print("\n--- 阶段1: 检查 ---")
    warmup_ok, _ = check_warmup_date()
    lifecycle_ok, _ = check_lifecycle_api()
    print()

    if warmup_ok and lifecycle_ok:
        print("✅ 所有检查通过，无需修复")
        return True

    # 2. 触发修复
    print("\n--- 阶段2: 触发 Data Agent 修复 ---")
    fix_ok = trigger_data_agent()
    print()

    if not fix_ok:
        print("❌ Data Agent 修复失败")
        return False

    # 3. 验证
    print("\n--- 阶段3: 验证修复结果 ---")
    verify_ok = verify_after_fix()
    print()

    if verify_ok:
        print("✅ 修复验证通过，问题已解决")
        return True
    else:
        print("❌ 修复验证失败，需要进一步调查")
        return False


def watch_mode():
    """持续监控模式"""
    print("\n" + "=" * 60)
    print("👀 Leader 持续监控模式（Ctrl+C 退出）")
    print("=" * 60 + "\n")

    last_status = True
    while True:
        try:
            print("\n--- " + datetime.now().strftime("%H:%M:%S") + " ---")

            warmup_ok, _ = check_warmup_date()
            lifecycle_ok, _ = check_lifecycle_api()

            all_ok = warmup_ok and lifecycle_ok

            if all_ok:
                print("✅ 状态正常")
            else:
                print("⚠️  状态异常，触发修复...")
                fix_ok = trigger_data_agent()
                if fix_ok:
                    verify_ok = verify_after_fix()
                    if verify_ok:
                        print("✅ 异常已自动修复")
                    else:
                        print("❌ 自动修复失败，请手动检查")
                else:
                    print("❌ Data Agent 修复失败")

            last_status = all_ok

            # 交易时间内每分钟检查，非交易时间每5分钟
            time.sleep(60 if is_trading_time() else 300)

        except KeyboardInterrupt:
            print("\n\n👋 监控退出")
            break
        except Exception as e:
            log(f"监控异常: {e}", "❌")
            time.sleep(60)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        daily_check()
    elif cmd == "full":
        full_workflow()
    elif cmd == "watch":
        watch_mode()
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
