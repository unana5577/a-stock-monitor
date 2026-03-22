#!/usr/bin/env python3
"""
清洁工：过期分时数据清理工具
保留7个自然日内的分时数据，清理更早的 minute-*.jsonl 文件
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path


def get_file_size_str(size_bytes):
    """转换字节为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def scan_temporary_files():
    """扫描需要清理的临时文件（仅分时数据）"""
    data_dir = Path("data")
    if not data_dir.exists():
        print(f"❌ data/ 目录不存在")
        return []

    # 计算阈值：今天 - 7个自然日
    threshold = datetime.now() - timedelta(days=7)
    print(f"📅 清理阈值：{threshold.strftime('%Y-%m-%d %H:%M:%S')}（7天前）")
    print("")

    # 仅匹配分时数据文件
    pattern = re.compile(r"minute-(\d{8})\.jsonl$")

    files_to_clean = []
    total_size = 0

    for file in data_dir.glob("minute-*.jsonl"):
        if file.is_file():
            match = pattern.search(file.name)
            if match:
                date_str = match.group(1)
                try:
                    file_date = datetime.strptime(date_str, "%Y%m%d")

                    # 检查是否早于阈值
                    if file_date < threshold:
                        size = file.stat().st_size
                        files_to_clean.append({
                            'path': file,
                            'name': file.name,
                            'date': file_date,
                            'size': size,
                            'size_str': get_file_size_str(size)
                        })
                        total_size += size
                except ValueError:
                    continue

    # 按日期排序
    files_to_clean.sort(key=lambda x: x['date'])

    return files_to_clean, total_size


def generate_clean_plan(files_to_clean, total_size):
    """生成清理计划"""
    plan = []
    plan.append("=" * 60)
    plan.append("🧹 建议清理清单")
    plan.append("=" * 60)
    plan.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    plan.append("")

    if not files_to_clean:
        plan.append("✨ 没有需要清理的文件")
        plan.append("")
        plan.append("=" * 60)
        return "\n".join(plan)

    plan.append(f"📦 文件数量：{len(files_to_clean)} 个")
    plan.append(f"💾 预估释放：{get_file_size_str(total_size)}")
    plan.append("")
    plan.append("文件列表：")
    plan.append("")

    for i, file_info in enumerate(files_to_clean, 1):
        plan.append(
            f"  {i:2d}. {file_info['name']}"
            f" | {file_info['date'].strftime('%Y-%m-%d')}"
            f" | {file_info['size_str']}"
        )

    plan.append("")
    plan.append("=" * 60)
    plan.append("⚠️  注意：这些文件将被永久删除！")
    plan.append("=" * 60)

    return "\n".join(plan)


def confirm_cleanup():
    """询问用户确认"""
    print("")
    response = input("确认清理吗？(yes/no): ").strip().lower()
    return response in ['yes', 'y', '是', '确认']


def execute_cleanup(files_to_clean):
    """执行清理操作"""
    print("")
    print("🚀 开始清理...")

    success_count = 0
    failed_count = 0

    for file_info in files_to_clean:
        try:
            file_info['path'].unlink()
            print(f"  ✅ {file_info['name']}")
            success_count += 1
        except Exception as e:
            print(f"  ❌ {file_info['name']} - {e}")
            failed_count += 1

    print("")
    print(f"✨ 清理完成！成功 {success_count} 个，失败 {failed_count} 个")

    return success_count, failed_count


def main():
    """主函数"""
    print("🧹 清洁工：开始扫描过期分时数据...")
    print("   清理范围：仅 minute-*.jsonl 文件")
    print("   保留策略：7个自然日内")
    print("")

    # 扫描需要清理的文件
    files_to_clean, total_size = scan_temporary_files()

    # 生成清理计划
    plan = generate_clean_plan(files_to_clean, total_size)
    print(plan)

    # 如果没有文件需要清理，直接退出
    if not files_to_clean:
        return

    # 询问确认
    if not confirm_cleanup():
        print("")
        print("❌ 已取消清理操作")
        return

    # 执行清理
    success_count, failed_count = execute_cleanup(files_to_clean)

    # 如果全部成功，更新一下统计
    if failed_count == 0:
        print("")
        print(f"💾 已释放空间：{get_file_size_str(total_size)}")


if __name__ == "__main__":
    main()
