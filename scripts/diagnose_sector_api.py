#!/usr/bin/env python3
"""
Data Agent 诊断工具 - 诊断板块接口问题

功能：
1. 检查 lifecycle 接口返回是否为空
2. 测试 ETF 数据源是否可用
3. 接口OK → 触发 warmup 更新
4. 接口坏 → 执行分时回补日线数据

使用：
  python scripts/diagnose_sector_api.py check     # 只诊断，不修复
  python scripts/diagnose_sector_api.py fix       # 诊断 + 修复
  python scripts/diagnose_sector_api.py full       # 完整诊断 + 修复 + 验证
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
        return now.strftime("%Y-%m-%d")
    else:
        days_back = 1
        while days_back <= 7:
            check = now - timedelta(days=days_back)
            if check.weekday() < 5:
                return check.strftime("%Y-%m-%d")
            days_back += 1
        return now.strftime("%Y-%m-%d")


def check_lifecycle_api():
    """检查 /api/sector/lifecycle 接口"""
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

            log(f"lifecycle 返回: day={day}, items={len(items)}", "📊")

            if len(items) == 0:
                log("问题确认: lifecycle 返回空数据", "❌")
                return False, reason or "empty_items"
            else:
                log("lifecycle 接口正常", "✅")
                return True, ""
    except Exception as e:
        log(f"lifecycle 接口请求失败: {e}", "❌")
        return False, f"request_error: {e}"


def check_warmup_date():
    """检查 warmup 文件日期"""
    log("检查 warmup 文件日期...", "🔍")

    warmup_file = DATA_DIR / "sector-history-warmup-60.json"
    if not warmup_file.exists():
        log("warmup 文件不存在", "❌")
        return False, "warmup_not_found"

    mtime = datetime.fromtimestamp(warmup_file.stat().st_mtime)
    expected_day = get_expected_latest_date()

    # 检查文件内容的日期
    try:
        with open(warmup_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 找任意一个板块的最后日期
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
                    return False, f"warmup_stale: {file_date}"
    except Exception as e:
        log(f"warmup 文件读取失败: {e}", "❌")
        return False, f"warmup_read_error: {e}"

    return False, "warmup_date_unknown"


def test_etf_data_source():
    """测试 ETF 数据源是否可用"""
    log("测试 ETF 数据源...", "🔍")

    try:
        # 读取 proxy 配置
        proxy_file = DATA_DIR / "sector-proxy.json"
        if not proxy_file.exists():
            log("sector-proxy.json 不存在", "❌")
            return False, "proxy_not_found"

        with open(proxy_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        etf_map = cfg.get("variants", {}).get("etf", {})
        if not etf_map:
            log("etf 配置为空", "❌")
            return False, "etf_config_empty"

        # 测试第一个 ETF
        first_etf = list(etf_map.values())[0]
        log(f"测试 ETF: {first_etf}", "📊")

        import urllib.request
        # 测试腾讯日线接口
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={first_etf},day,,,10,qfq&r=0.1"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode()
            if "error" in text.lower() or "null" in text:
                log("腾讯 ETF 接口返回异常", "❌")
                return False, "tencent_api_error"
            else:
                log("腾讯 ETF 接口正常", "✅")
                return True, ""

    except Exception as e:
        log(f"ETF 数据源测试失败: {e}", "❌")
        return False, f"etf_source_error: {e}"


def update_warmup():
    """触发 warmup 更新"""
    log("触发 warmup 更新...", "🔄")

    try:
        # 调用 server.js 的 warmup 接口
        import urllib.request
        url = "http://127.0.0.1:8787/api/warmup"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            log(f"warmup 更新结果: {result}", "📊")
            return True
    except Exception as e:
        log(f"warmup 更新失败: {e}", "❌")
        return False


def backfill_from_minute():
    """分时回补日线数据"""
    log("执行分时回补...", "🔄")

    try:
        # 读取分时数据，转换为日线
        # 策略：从最近的warmup读取前一天 + 今天分时聚合
        warmup_file = DATA_DIR / "sector-history-warmup-60.json"
        if not warmup_file.exists():
            log("无法回补：warmup 文件不存在", "❌")
            return False

        log("分时回补需要手动处理，请检查分时数据完整性", "⚠️")
        return False

    except Exception as e:
        log(f"分时回补失败: {e}", "❌")
        return False


def fix_lifecycle():
    """修复 lifecycle 数据"""
    log("修复 lifecycle 数据...", "🔧")

    # 方案1：重新请求接口
    log("尝试重新请求 lifecycle 接口...", "🔄")
    lifecycle_ok, _ = check_lifecycle_api()
    if lifecycle_ok:
        log("lifecycle 接口已恢复", "✅")
        return True

    # 方案2：更新 warmup
    log("尝试更新 warmup...", "🔄")
    if update_warmup():
        time.sleep(2)
        lifecycle_ok, _ = check_lifecycle_api()
        if lifecycle_ok:
            log("warmup 更新后 lifecycle 恢复", "✅")
            return True

    # 方案3：分时回补
    log("尝试分时回补...", "🔄")
    if backfill_from_minute():
        lifecycle_ok, _ = check_lifecycle_api()
        if lifecycle_ok:
            log("分时回补后 lifecycle 恢复", "✅")
            return True

    log("所有修复方案均失败，请手动检查", "🚨")
    return False


def verify_frontend():
    """验证前端渲染"""
    log("验证前端渲染...", "🔍")

    lifecycle_ok, _ = check_lifecycle_api()
    warmup_ok, _ = check_warmup_date()

    if lifecycle_ok and warmup_ok:
        log("前端数据完整，可以正常渲染", "✅")
        return True
    else:
        log("前端数据仍有问题", "❌")
        return False


def full_check():
    """完整诊断流程"""
    print("\n" + "=" * 60)
    print("🔍 Data Agent 诊断 - 完整检查")
    print("=" * 60 + "\n")

    # 1. 检查 lifecycle 接口
    lifecycle_ok, lifecycle_reason = check_lifecycle_api()
    print()

    # 2. 检查 warmup 日期
    warmup_ok, warmup_reason = check_warmup_date()
    print()

    # 3. 测试 ETF 数据源
    etf_ok, etf_reason = test_etf_data_source()
    print()

    # 汇总
    print("=" * 60)
    print("📊 诊断汇总")
    print("=" * 60)
    print(f"  lifecycle 接口: {'✅ 正常' if lifecycle_ok else '❌ 异常'}")
    print(f"  warmup 日期:   {'✅ 最新' if warmup_ok else '❌ 过期'}")
    print(f"  ETF 数据源:   {'✅ 可用' if etf_ok else '❌ 不可用'}")
    print("=" * 60)

    if lifecycle_ok and warmup_ok:
        print("✅ 所有检查通过，无需修复")
        return True
    else:
        print("⚠️  发现问题，建议执行 fix")
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        full_check()
    elif cmd == "fix":
        print("\n" + "=" * 60)
        print("🔧 Data Agent 修复流程")
        print("=" * 60 + "\n")

        lifecycle_ok, _ = check_lifecycle_api()
        if lifecycle_ok:
            print("lifecycle 接口正常，无需修复")
        else:
            print()
            fix_lifecycle()

        print()
        verify_frontend()

    elif cmd == "full":
        print("\n" + "=" * 60)
        print("🔍 + 🔧 Data Agent 完整流程（诊断 + 修复 + 验证）")
        print("=" * 60 + "\n")

        if not full_check():
            print()
            fix_lifecycle()
            print()
            verify_frontend()

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
