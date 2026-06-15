#!/usr/bin/env python3
import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def cleanup_directory(base_dir: Path, keep_days: int, apply: bool) -> tuple[int, int, str]:
    """
    清理指定分钟数据目录下的过期文件。
    返回: (deleted_count, kept_count, oldest_kept_date)
    """
    if not base_dir.exists():
        return 0, 0, ""

    deleted_files = 0
    kept_files = 0
    oldest_kept_date = ""

    for code_dir in base_dir.iterdir():
        if not code_dir.is_dir():
            continue
            
        files = list(code_dir.glob("*.jsonl"))
        files.sort(key=lambda f: f.name, reverse=True)
        
        files_to_keep = files[:keep_days]
        files_to_delete = files[keep_days:]
        
        kept_files += len(files_to_keep)
        
        if len(files_to_keep) > 0:
            current_oldest = files_to_keep[-1].name[:10]
            if not oldest_kept_date or current_oldest < oldest_kept_date:
                oldest_kept_date = current_oldest
        
        for f in files_to_delete:
            if apply:
                f.unlink()
            print(f"  [{'DELETED' if apply else 'DRY-RUN'}] {f.relative_to(PROJECT_ROOT)}")
            deleted_files += 1

        if apply and not any(code_dir.iterdir()):
            code_dir.rmdir()
            print(f"  [{'DELETED' if apply else 'DRY-RUN'}] Empty directory {code_dir.relative_to(PROJECT_ROOT)}")

    return deleted_files, kept_files, oldest_kept_date


def cleanup_dated_files(files: list[Path], keep_days: int, apply: bool) -> tuple[int, int, str]:
    uniq: dict[str, Path] = {}
    for f in files:
        try:
            key = str(f.resolve())
        except Exception:
            key = str(f)
        if key not in uniq:
            uniq[key] = f
    files = [f for f in uniq.values() if f.exists()]
    files.sort(key=lambda f: f.name, reverse=True)
    files_to_keep = files[:keep_days]
    files_to_delete = files[keep_days:]
    for f in files_to_delete:
        if apply:
            try:
                f.unlink()
            except FileNotFoundError:
                continue
        print(f"  [{'DELETED' if apply else 'DRY-RUN'}] {f.relative_to(PROJECT_ROOT)}")
    oldest = files_to_keep[-1].name[:10] if files_to_keep else "N/A"
    return len(files_to_delete), len(files_to_keep), oldest


def cleanup_intraday_snapshots(keep_days: int, apply: bool) -> int:
    base = PROJECT_ROOT / "data" / "lifecycle" / "intraday"
    print(f"\n> 扫描 Intraday 快照目录: {base.relative_to(PROJECT_ROOT)}")
    if not base.exists():
        return 0
    files = list(base.glob("etf_snapshot_*.jsonl")) + list(base.glob("etf_????-??-??.jsonl"))
    deleted, kept, oldest = cleanup_dated_files(files, keep_days, apply)
    print(f"  => 完毕。保留了 {kept} 个文件，清理了 {deleted} 个文件。最远保留至: {oldest}")
    return deleted


def cleanup_warmup_history(keep_days: int, apply: bool) -> int:
    base = PROJECT_ROOT / "data" / "warmup"
    print(f"\n> 扫描 Warmup 历史目录: {base.relative_to(PROJECT_ROOT)}")
    if not base.exists():
        return 0
    files = list(base.glob("warmup-????-??-??-60.json"))
    deleted, kept, oldest = cleanup_dated_files(files, keep_days, apply)
    print(f"  => 完毕。保留了 {kept} 个文件，清理了 {deleted} 个文件。最远保留至: {oldest}")
    return deleted


def cleanup_lifecycle_history(keep_days: int, apply: bool) -> int:
    base = PROJECT_ROOT / "data" / "lifecycle"
    print(f"\n> 扫描 Lifecycle 历史目录: {base.relative_to(PROJECT_ROOT)}")
    if not base.exists():
        return 0
    files = list(base.glob("lifecycle-????-??-??.json"))
    deleted, kept, oldest = cleanup_dated_files(files, keep_days, apply)
    print(f"  => 完毕。保留了 {kept} 个文件，清理了 {deleted} 个文件。最远保留至: {oldest}")
    return deleted


def cleanup_flat_minute_files(keep_days: int, apply: bool) -> int:
    """清理 data/ 根目录旧的扁平分钟线文件 `minute-YYYYMMDD-code.jsonl`"""
    base = PROJECT_ROOT / "data"
    print(f"\n> 扫描旧版 Flat 分钟线文件: {base.relative_to(PROJECT_ROOT)}")
    if not base.exists():
        return 0
    files = list(base.glob("minute-*.jsonl"))
    files = [f for f in files if len(f.stem) >= len("minute-20260508") and f.stem.startswith("minute-")]
    files.sort(key=lambda f: f.name, reverse=True)

    seen_dates: set[str] = set()
    for f in files:
        parts = f.stem.split("-")
        if len(parts) >= 2:
            seen_dates.add(parts[1])

    allowed_dates = sorted(seen_dates, reverse=True)[:keep_days]
    deleted = 0
    for f in files:
        parts = f.stem.split("-")
        date_part = parts[1] if len(parts) >= 2 else ""
        if date_part not in allowed_dates:
            if apply:
                f.unlink()
            print(f"  [{'DELETED' if apply else 'DRY-RUN'}] {f.relative_to(PROJECT_ROOT)}")
            deleted += 1
    print(f"  => 完毕。保留了 {len(allowed_dates)} 个日期组，清理了 {deleted} 个文件。保留日期: {', '.join(sorted(allowed_dates))}")
    return deleted


def cleanup_archive_history(keep_days: int, apply: bool) -> int:
    base = PROJECT_ROOT / "data"
    print(f"\n> 扫描 Archive 历史目录: {base.relative_to(PROJECT_ROOT)}")
    if not base.exists():
        return 0
    files = list(base.glob("archive-*.jsonl"))
    files = [f for f in files if len(f.stem) >= len("archive-20260508") and f.stem.startswith("archive-") and f.stem[8:16].isdigit()]
    files.sort(key=lambda f: f.name, reverse=True)
    files_to_keep = files[:keep_days]
    files_to_delete = files[keep_days:]
    for f in files_to_delete:
        if apply:
            f.unlink()
        print(f"  [{'DELETED' if apply else 'DRY-RUN'}] {f.relative_to(PROJECT_ROOT)}")
    oldest = files_to_keep[-1].stem[8:16] if files_to_keep else "N/A"
    print(f"  => 完毕。保留了 {len(files_to_keep)} 个文件，清理了 {len(files_to_delete)} 个文件。最远保留至: {oldest}")
    return len(files_to_delete)


def reset_breadth_cache(apply: bool) -> bool:
    """重置涨跌家数分钟级缓存文件（每天开盘前或盘后应清空，重新记录）"""
    cache_file = PROJECT_ROOT / "data" / "market" / "minute" / "breadth-cache.jsonl"
    if not cache_file.exists():
        return False
        
    if apply:
        cache_file.write_text("", encoding="utf-8")
        print(f"  [{'RESET' if apply else 'DRY-RUN'}] {cache_file.relative_to(PROJECT_ROOT)} (File emptied)")
    else:
        print(f"  [DRY-RUN] Would empty {cache_file.relative_to(PROJECT_ROOT)}")
        
    return True

def truncate_ai_logs(keep_days: int, apply: bool) -> int:
    """按行截断 AI 相关的追加型日志，只保留最近 N 天的数据"""
    import json
    from datetime import datetime, timedelta
    
    cutoff_date = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    
    ai_dir = PROJECT_ROOT / "data" / "market" / "ai"
    if not ai_dir.exists():
        return 0
        
    target_files = ["report.jsonl", "etf_report.jsonl", "snapshot.jsonl"]
    truncated_count = 0
    
    for filename in target_files:
        file_path = ai_dir / filename
        if not file_path.exists():
            continue
            
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
            if not lines:
                continue
                
            kept_lines = []
            for line in lines:
                try:
                    data = json.loads(line)
                    if data.get("date", "") >= cutoff_date:
                        kept_lines.append(line)
                except:
                    kept_lines.append(line)
                    
            if len(kept_lines) < len(lines):
                if apply:
                    file_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")
                print(f"  [{'TRUNCATED' if apply else 'DRY-RUN'}] {file_path.relative_to(PROJECT_ROOT)} (Kept {len(kept_lines)}/{len(lines)} lines)")
                truncated_count += 1
            else:
                print(f"  [SKIPPED] {file_path.relative_to(PROJECT_ROOT)} (All {len(lines)} lines are within {keep_days} days)")
                
        except Exception as e:
            print(f"  [ERROR] 处理 {filename} 时出错: {e}")
            
    return truncated_count


def main() -> int:
    parser = argparse.ArgumentParser(description="清理 M1 阶段过期的分钟级分时数据")
    parser.add_argument("--keep-days", type=int, default=3, help="保留最近 N 个交易日的文件 (默认 3)")
    parser.add_argument("--apply", action="store_true", help="如果带有此标志，则实际执行删除，否则仅打印 (dry-run)")
    args = parser.parse_args()

    mode_str = "实际执行 (APPLY)" if args.apply else "试运行 (DRY-RUN)"
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 启动分钟文件清理任务... 模式: {mode_str}, 保留天数: {args.keep_days}")

    total_deleted = 0
    
    # 1. 清理大盘指数分时
    index_minute_dir = PROJECT_ROOT / "data" / "index" / "minute"
    print(f"\n> 扫描 Index 分时目录: {index_minute_dir.relative_to(PROJECT_ROOT)}")
    deleted, kept, index_oldest = cleanup_directory(index_minute_dir, args.keep_days, args.apply)
    total_deleted += deleted
    print(f"  => 完毕。保留了 {kept} 个文件，清理了 {deleted} 个文件。最远保留至: {index_oldest or 'N/A'}")

    # 2. 清理 ETF 分时
    etf_minute_dir = PROJECT_ROOT / "data" / "etf" / "minute"
    print(f"\n> 扫描 ETF 分时目录: {etf_minute_dir.relative_to(PROJECT_ROOT)}")
    deleted, kept, etf_oldest = cleanup_directory(etf_minute_dir, args.keep_days, args.apply)
    total_deleted += deleted
    print(f"  => 完毕。保留了 {kept} 个文件，清理了 {deleted} 个文件。最远保留至: {etf_oldest or 'N/A'}")

    # 3. 清理 Sector (板块) 分时
    sector_minute_dir = PROJECT_ROOT / "data" / "sector" / "minute"
    print(f"\n> 扫描 Sector 分时目录: {sector_minute_dir.relative_to(PROJECT_ROOT)}")
    deleted, kept, sector_oldest = cleanup_directory(sector_minute_dir, args.keep_days, args.apply)
    total_deleted += deleted
    print(f"  => 完毕。保留了 {kept} 个文件，清理了 {deleted} 个文件。最远保留至: {sector_oldest or 'N/A'}")
    
    # 4. 清理全市场成交额分时
    market_amount_minute_dir = PROJECT_ROOT / "data" / "market" / "minute" / "amount"
    print(f"\n> 扫描 Market Amount 分时目录: {market_amount_minute_dir.relative_to(PROJECT_ROOT)}")
    if market_amount_minute_dir.exists():
        files = list(market_amount_minute_dir.glob("*.jsonl"))
        files.sort(key=lambda f: f.name, reverse=True)
        files_to_keep = files[:args.keep_days]
        files_to_delete = files[args.keep_days:]
        
        for f in files_to_delete:
            if args.apply:
                f.unlink()
            print(f"  [{'DELETED' if args.apply else 'DRY-RUN'}] {f.relative_to(PROJECT_ROOT)}")
            total_deleted += 1
        
        amount_oldest = files_to_keep[-1].name[:10] if files_to_keep else 'N/A'
        print(f"  => 完毕。保留了 {len(files_to_keep)} 个文件，清理了 {len(files_to_delete)} 个文件。最远保留至: {amount_oldest}")

    # 5. 重置涨跌家数缓存
    print("\n> 重置涨跌家数情绪分时缓存...")
    if reset_breadth_cache(args.apply):
        total_deleted += 1

    # 6. 截断 AI 日志 (按行)
    print(f"\n> 截断 AI 日志文件 (保留 {args.keep_days} 天)...")
    truncated_ai = truncate_ai_logs(args.keep_days, args.apply)
    total_deleted += truncated_ai

    # 7. 清理 Intraday 快照、Warmup、Lifecycle、Archive 历史文件
    total_deleted += cleanup_intraday_snapshots(args.keep_days, args.apply)
    total_deleted += cleanup_warmup_history(args.keep_days, args.apply)
    total_deleted += cleanup_lifecycle_history(args.keep_days, args.apply)
    total_deleted += cleanup_archive_history(args.keep_days, args.apply)

    # 8. 清理旧版 Flat 分钟线文件
    total_deleted += cleanup_flat_minute_files(args.keep_days, args.apply)

    print(f"\n🎉 任务结束。共处理 (删除/清空/截断) {total_deleted} 个目标。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
