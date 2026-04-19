import json
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def build_warmup(days=60):
    warmup_data = {}
    latest_day = "1970-01-01"
    
    # Collect indices
    index_dir = PROJECT_ROOT / "data/index/daily"
    if index_dir.exists():
        for symbol in os.listdir(index_dir):
            if symbol.startswith('.'): continue
            daily_file = index_dir / symbol / "daily.jsonl"
            if daily_file.exists():
                lines = daily_file.read_text(encoding="utf-8").strip().splitlines()
                lines = lines[-days:]
                records = [json.loads(line) for line in lines]
                if records:
                    warmup_data[symbol] = records
                    if records[-1].get("date", "") > latest_day:
                        latest_day = records[-1]["date"]
                
    # Collect etfs
    etf_dir = PROJECT_ROOT / "data/etf/daily"
    if etf_dir.exists():
        for symbol in os.listdir(etf_dir):
            if symbol.startswith('.'): continue
            daily_file = etf_dir / symbol / "daily.jsonl"
            if daily_file.exists():
                lines = daily_file.read_text(encoding="utf-8").strip().splitlines()
                lines = lines[-days:]
                records = [json.loads(line) for line in lines]
                if records:
                    warmup_data[symbol] = records
                    if records[-1].get("date", "") > latest_day:
                        latest_day = records[-1]["date"]
                        
    if latest_day == "1970-01-01":
        latest_day = datetime.now().strftime("%Y-%m-%d")
                
    output_payload = {
        "day": latest_day,
        "history": warmup_data
    }
                
    # Save to data/warmup/warmup-{latest_day}-{days}.json
    out_dir = PROJECT_ROOT / "data/warmup"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"warmup-{latest_day}-{days}.json"
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False)
        
    # 同时创建一个 fixed 名字的软链接/复制，方便前端固定路径请求最新版
    fixed_file = out_dir / f"warmup-{days}.json"
    with open(fixed_file, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False)
        
    print(f"✅ M1-Warmup 成功！数据日期: {latest_day}, 共聚合 {len(warmup_data)} 个标的, 已保存至 {out_file.relative_to(PROJECT_ROOT)}")
    return 0

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=60)
    args = p.parse_args()
    exit(build_warmup(args.days))
