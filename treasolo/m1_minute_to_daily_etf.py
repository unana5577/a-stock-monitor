import json
import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def run_minute_to_daily_etf(symbol: str, day: str):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在执行 M1-D: ETF分时转日线 ({symbol})")
    
    m1_etf_dir = PROJECT_ROOT / "data" / "m1" / "etf" / symbol
    daily_file = m1_etf_dir / "daily.jsonl"
    minute_file = PROJECT_ROOT / f"data/market/minute/{symbol}/{day}.jsonl"
    
    if not minute_file.exists():
        print(f"  ❌ 找不到当天的 ETF 分时文件: {minute_file.relative_to(PROJECT_ROOT)}")
        return 1
        
    # 读取今天的最后一条分时数据，提取现成的指标
    try:
        minute_lines = minute_file.read_text(encoding="utf-8").splitlines()
        if not minute_lines:
            print("  ❌ ETF 分时文件为空")
            return 1
            
        last_minute = json.loads(minute_lines[-1])
        
        current_close = float(last_minute.get("price", 0))
        current_open = float(last_minute.get("open", 0))
        current_high = float(last_minute.get("high", 0))
        current_low = float(last_minute.get("low", 0))
        current_pct = float(last_minute.get("pct", 0))
        current_amount = float(last_minute.get("amount", 0))
        current_vol = float(last_minute.get("vol", 0))
            
    except Exception as e:
        print(f"  ❌ 解析 ETF 分时文件失败: {e}")
        return 1
        
    # 组装新日线记录
    new_daily_record = {
        "date": day,
        "open": round(current_open, 3),
        "high": round(current_high, 3),
        "low": round(current_low, 3),
        "close": round(current_close, 3),
        "pct": round(current_pct, 2),
        "amount": current_amount,
        "vol": current_vol
    }
    
    # 落盘
    m1_etf_dir.mkdir(parents=True, exist_ok=True)
    
    if daily_file.exists():
        daily_lines = daily_file.read_text(encoding="utf-8").splitlines()
        last_daily = json.loads(daily_lines[-1]) if daily_lines else {}
        
        if last_daily.get("date") == day:
            print("  ⚠️ 今天的数据已存在，执行更新(覆盖最后一行)")
            daily_lines[-1] = json.dumps(new_daily_record)
            daily_file.write_text("\n".join(daily_lines) + "\n", encoding="utf-8")
        else:
            print("  ✅ 追加今天的全新日线")
            with open(daily_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(new_daily_record) + "\n")
    else:
        print("  ✅ 创建并写入全新的 ETF 日线表")
        with open(daily_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(new_daily_record) + "\n")
            
    # 更新 Meta
    meta_file = m1_etf_dir / "daily.jsonl.meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["asOf"] = datetime.now().isoformat()
            meta["endDate"] = day
            meta["recordCount"] = len(daily_file.read_text(encoding="utf-8").splitlines())
            meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass
    else:
        meta = {
            "datasetId": "etf_daily",
            "providerId": "minute_to_daily",
            "symbol": symbol,
            "asOf": datetime.now().isoformat(),
            "endDate": day,
            "recordCount": len(daily_file.read_text(encoding="utf-8").splitlines())
        }
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"  ✅ 成功！生成了 {day} 的 ETF 日线: close={current_close}, pct={current_pct}%")
    return 0

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--day", default="")
    args = p.parse_args()
    
    day = args.day or datetime.now().strftime("%Y-%m-%d")
    sys.exit(run_minute_to_daily_etf(args.symbol, day))