#!/usr/bin/env python3
"""
warmup内容验证工具 - 验证 sector-history-warmup-60.json 数据内容
"""

import json
from pathlib import Path


def verify_warmup_content():
    """验证warmup文件内容"""
    log_output("\n📊 warmup文件内容验证")

    warmup_file = Path("data/sector-history-warmup-60.json")

    if not warmup_file.exists():
        log_output("   ❌ warmup文件不存在")
        return False

    # 读取文件
    with open(warmup_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 验证基本结构
    day = data.get('day')
    history = data.get('history', {})
    minute = data.get('minute', {})
    watch = data.get('watch', [])
    variant = data.get('variant')

    log_output(f"   📅 数据日期: {day or 'N/A'}")
    log_output(f"   🔧 Variant: {variant or 'N/A'}")

    # ✅ 正确的板块数量统计
    sector_count = len(history)
    log_output(f"   📊 板块数量: {sector_count}")

    if sector_count == 0:
        log_output("   ❌ 没有板块数据")
        return False

    # 验证每个板块的数据
    log_output(f"   📈 History 数据:")
    for sector, hist in history.items():
        if isinstance(hist, list):
            log_output(f"      {sector}: {len(hist)} 条")
        else:
            log_output(f"      {sector}: 格式错误")

    log_output(f"   ⏱️  Minute 数据:")
    minute_count = len([k for k in minute.keys() if minute.get(k)])
    log_output(f"      有数据的板块: {minute_count}/{sector_count}")

    # 验证 watch 列表
    if isinstance(watch, list):
        log_output(f"   👀 Watch 列表: {', '.join(watch)}")
    else:
        log_output(f"   👀 Watch 列表: {watch}")

    # 验证数据完整性
    all_60_days = all(isinstance(hist, list) and len(hist) == 60 for hist in history.values())
    if all_60_days:
        log_output(f"   ✅ 所有板块都是60天数据")
        return True
    else:
        log_output(f"   ⚠️  部分板块数据不是60天")
        return False


def log_output(message):
    """输出到stdout"""
    print(message)


def main():
    """主函数"""
    log_output("=" * 60)
    log_output("warmup内容验证")
    log_output("=" * 60)

    result = verify_warmup_content()

    log_output("=" * 60)
    if result:
        log_output("✅ warmup内容验证通过")
    else:
        log_output("⚠️  warmup内容存在问题")
    log_output("=" * 60)


if __name__ == "__main__":
    main()
