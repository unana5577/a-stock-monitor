import json
import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def run_minute_to_daily_etf(symbol: str, day: str):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在执行 M1-D: ETF分时转日线 ({symbol})")
    
    m1_etf_dir = PROJECT_ROOT / "data" / "etf" / "daily" / symbol
    daily_file = m1_etf_dir / "daily.jsonl"
    minute_file = PROJECT_ROOT / f"data/etf/minute/{symbol}/{day}.jsonl"
    
    if not minute_file.exists():
        print(f"  ❌ 找不到当天的 ETF 分时文件: {minute_file.relative_to(PROJECT_ROOT)}")
        # 强制走回补逻辑
        minute_lines = []
    else:
        minute_lines = minute_file.read_text(encoding="utf-8").splitlines()
        
    # 判断是否完整：至少 238 条，且最后一条包含 15:00
    is_complete = False
    if len(minute_lines) >= 238:
        try:
            last_obj = json.loads(minute_lines[-1])
            if last_obj.get("asOf") == "15:00" or "15:00" in str(last_obj.get("time", "")):
                is_complete = True
        except:
            pass

    # ==========================================
    # 分支 B: 本地分时不完整，触发官方历史接口回补
    # ==========================================
    if not is_complete:
        print(f"  ⚠️ 分时数据不完整 (共 {len(minute_lines)} 条)，触发官方历史分钟线回补...")
        try:
            import requests
            
            clean_code = symbol.replace("sh", "").replace("sz", "")
            day_str = day.replace("-", "")
            
            # 使用更稳定的腾讯分钟线接口
            url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={symbol},m1,,240"
            resp = requests.get(url, timeout=5)
            data = resp.json().get("data", {}).get(symbol, {}).get("m1", [])
            
            if not data:
                print("  ❌ 官方历史分钟线回补失败: 接口返回空数据")
                return 1
                
            # 拿到完整的 K 线，覆盖重写本地分时文件
            minute_lines = []
            for row in data:
                # 腾讯格式: [时间"202604220931", 开盘, 收盘, 最高, 最低, 成交量, 附加信息, 成交额(万元)]
                time_raw = str(row[0])
                if not time_raw.startswith(day_str): continue
                
                # 格式化时间 "2026-04-22 09:31:00"
                formatted_time = f"{time_raw[:4]}-{time_raw[4:6]}-{time_raw[6:8]} {time_raw[8:10]}:{time_raw[10:12]}:00"
                as_of = f"{time_raw[8:10]}:{time_raw[10:12]}"
                
                record = {
                    "time": formatted_time,
                    "asOf": as_of,
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "price": float(row[2]),
                    "vol": float(row[5]),
                    "amount": float(row[5]) * 100 * float(row[2]),
                    "pct": 0.0
                }
                minute_lines.append(json.dumps(record, ensure_ascii=False))
                
            # 重写本地文件
            minute_file.parent.mkdir(parents=True, exist_ok=True)
            minute_file.write_text("\n".join(minute_lines) + "\n", encoding="utf-8")
            print(f"  ✅ 官方回补成功，已重写本地文件 (共 {len(minute_lines)} 条)")
            
        except Exception as e:
            print(f"  ❌ 官方历史分钟线回补报错: {e}")
            return 1

    # ==========================================
    # 读取最终的分时数据，合成日线
    # ==========================================
    try:
        last_minute = json.loads(minute_lines[-1])
        current_close = float(last_minute.get("price", 0) or last_minute.get("close", 0))
        
        # 为了准确计算 pct，尝试从本地日线文件中获取昨收
        prev_close = None
        if daily_file.exists():
            daily_lines = daily_file.read_text(encoding="utf-8").splitlines()
            for line in reversed(daily_lines):
                if not line.strip(): continue
                obj = json.loads(line)
                if obj.get("date") and obj["date"] < day:
                    prev_close = float(obj.get("close", 0))
                    break
        
        # 计算当天的真实 OHLC
        highs, lows = [], []
        first_open = None
        amounts, vols = [], []
        
        for l in minute_lines:
            try:
                obj = json.loads(l)
                if first_open is None and obj.get("open"): first_open = float(obj["open"])
                if obj.get("high"): highs.append(float(obj["high"]))
                if obj.get("low"): lows.append(float(obj["low"]))
                if obj.get("amount"): amounts.append(float(obj["amount"]))
                if obj.get("vol"): vols.append(float(obj["vol"]))
            except: pass
            
        current_open = first_open if first_open is not None else current_close
        current_high = max(highs) if highs else current_close
        current_low = min(lows) if lows else current_close
        
        # 核心逻辑：判断数据口径
        if is_complete:
            # 分支 A: 本地抓取完整，amount 是累计总额，直接取最后一条
            current_amount = float(last_minute.get("amount", 0))
            current_vol = float(last_minute.get("vol", 0))
            print(f"  ✅ [数据口径] 本地完整，直接取最后一条累计值 (Amount: {current_amount:,.2f})")
        else:
            # 分支 B: 走过官方回补，amount 是单根 K 线增量，必须 sum 加总
            current_amount = sum(amounts) if amounts else 0.0
            current_vol = sum(vols) if vols else 0.0
            print(f"  ✅ [数据口径] 官方回补，使用 sum() 加总全天增量 (Amount: {current_amount:,.2f})")
            
        # 计算准确的全天 pct
        if prev_close and prev_close > 0:
            current_pct = (current_close - prev_close) / prev_close * 100
        else:
            current_pct = (current_close - current_open) / current_open * 100 if current_open > 0 else 0.0
            
    except Exception as e:
        print(f"  ❌ 合成日线指标失败: {e}")
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
