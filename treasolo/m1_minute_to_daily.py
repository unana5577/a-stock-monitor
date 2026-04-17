import json
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def run_minute_to_daily(symbol: str, day: str):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在执行 M1-B: 分时转日线 ({symbol})")
    
    m1_index_dir = PROJECT_ROOT / "data" / "index" / symbol
    daily_file = m1_index_dir / "daily.jsonl"
    minute_file = PROJECT_ROOT / f"data/index/minute/{symbol}/{day}.jsonl"
    
    if not daily_file.exists():
        print(f"  ❌ 底表不存在，请先执行 M1 历史回填: {daily_file.relative_to(PROJECT_ROOT)}")
        return 1
        
    if not minute_file.exists():
        print(f"  ❌ 找不到当天的分时文件: {minute_file.relative_to(PROJECT_ROOT)}")
        return 1
        
    # 1. 读取旧底表，找到昨收
    daily_lines = daily_file.read_text(encoding="utf-8").splitlines()
    if not daily_lines:
        print("  ❌ 底表为空")
        return 1
        
    try:
        last_daily = json.loads(daily_lines[-1])
        if last_daily.get("date") == day:
            # 如果今天已经写过了，那就拿倒数第二天的作为昨收
            if len(daily_lines) >= 2:
                prev_daily = json.loads(daily_lines[-2])
                prev_close = float(prev_daily.get("close", 0))
            else:
                prev_close = float(last_daily.get("open", 0)) # fallback
        else:
            prev_close = float(last_daily.get("close", 0))
    except Exception as e:
        print(f"  ❌ 解析底表失败: {e}")
        return 1
        
    if prev_close <= 0:
        print("  ❌ 昨收价异常 (<=0)")
        return 1
        
    # 2. 读取今天的最后一条分时数据
    try:
        minute_lines = minute_file.read_text(encoding="utf-8").splitlines()
        last_minute = json.loads(minute_lines[-1])
        
        # akshare 分时结构有最新价或者 close
        current_close = float(last_minute.get("price", last_minute.get("close", 0)))
        current_open = current_close # TODO: 从真正的分钟线头取
        current_high = current_close
        current_low = current_close
        
        for line in minute_lines:
            m = json.loads(line)
            p = float(m.get("price", m.get("close", 0)))
            if p > current_high: current_high = p
            if p < current_low: current_low = p
            
    except Exception as e:
        print(f"  ❌ 解析分时文件失败: {e}")
        return 1
        
    # 3. 严格计算 Pct
    pct = (current_close - prev_close) / prev_close * 100
    
    # 4. 组装新日线记录
    new_daily_record = {
        "date": day,
        "open": round(current_open, 2),
        "high": round(current_high, 2),
        "low": round(current_low, 2),
        "close": round(current_close, 2),
        "pct": round(pct, 2)
    }
    
    # 5. 落盘（覆盖还是追加）
    if last_daily.get("date") == day:
        print("  ⚠️ 今天的数据已存在，执行更新(覆盖最后一行)")
        daily_lines[-1] = json.dumps(new_daily_record)
        daily_file.write_text("\n".join(daily_lines) + "\n", encoding="utf-8")
    else:
        print("  ✅ 追加今天的全新日线")
        with open(daily_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(new_daily_record) + "\n")
            
    # 6. 更新 Meta，标记 providerId 为 minute_to_daily
    meta_file = m1_index_dir / "daily.jsonl.meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["providerId"] = "minute_to_daily"
            meta["asOf"] = datetime.now().isoformat()
            meta["endDate"] = day
            meta["recordCount"] = len(daily_lines) if last_daily.get("date") == day else len(daily_lines) + 1
            meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        except:
            pass
            
    print(f"  🎉 成功！合并生成了 {day} 的日线: close={new_daily_record['close']}, pct={new_daily_record['pct']}%")
    return 0

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="sh000001")
    p.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    args = p.parse_args()
    
    exit(run_minute_to_daily(args.symbol, args.day))

if __name__ == "__main__":
    main()