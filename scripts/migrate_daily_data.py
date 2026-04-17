#!/usr/bin/env python3
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 我们关注的核心标的，只有在这些列表里的才做迁移
INDEX_SYMBOLS = {
    "sh000001", "sz399001", "sz399006", 
    "sh000688", "sh000300", "sh000852"
}

ETF_SYMBOLS = {
    "sh511130", "sh511260", "sh512400", "sh512480",
    "sh515120", "sh515880", "sh516010", "sh516160",
    "sh516510", "sh562500", "sh563530"
}

def migrate_legacy_data():
    legacy_index_dir = PROJECT_ROOT / "data/index_daily"
    legacy_etf_dir = PROJECT_ROOT / "data/etf_daily"
    
    new_index_dir = PROJECT_ROOT / "data/index/daily"
    new_etf_dir = PROJECT_ROOT / "data/etf/daily"
    
    migrated_count = 0
    
    # 1. 迁移大盘指数
    if legacy_index_dir.exists():
        print("=== 开始迁移大盘指数 ===")
        for symbol in INDEX_SYMBOLS:
            code = symbol[-6:] # 提取六位数字
            legacy_file = legacy_index_dir / f"index_{code}.jsonl"
            if legacy_file.exists():
                # 目标路径: data/index/daily/sh000001/daily.jsonl
                target_dir = new_index_dir / symbol
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / "daily.jsonl"
                
                # 读取并拷贝（原封不动，回补脚本会处理格式）
                lines = legacy_file.read_text(encoding="utf-8").splitlines()
                target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                print(f"✅ 成功拷贝: {legacy_file.name} -> {target_file.relative_to(PROJECT_ROOT)} (共 {len(lines)} 行)")
                migrated_count += 1
            else:
                print(f"⚠️ 未找到旧底表: {legacy_file.name}")
                
    # 2. 迁移 ETF
    if legacy_etf_dir.exists():
        print("\n=== 开始迁移 ETF ===")
        for symbol in ETF_SYMBOLS:
            code = symbol[-6:]
            legacy_file = legacy_etf_dir / f"etf_{code}.jsonl"
            if legacy_file.exists():
                # 目标路径: data/etf/daily/sh511130/daily.jsonl
                target_dir = new_etf_dir / symbol
                target_dir.mkdir(parents=True, exist_ok=True)
                target_file = target_dir / "daily.jsonl"
                
                lines = legacy_file.read_text(encoding="utf-8").splitlines()
                target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                print(f"✅ 成功拷贝: {legacy_file.name} -> {target_file.relative_to(PROJECT_ROOT)} (共 {len(lines)} 行)")
                migrated_count += 1
            else:
                print(f"⚠️ 未找到旧底表: {legacy_file.name}")
                
    print(f"\n🎉 迁移拷贝完成！共成功处理 {migrated_count} 个标的。旧文件原封未动。")

if __name__ == "__main__":
    migrate_legacy_data()