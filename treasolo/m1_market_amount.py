import json
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_holidays() -> set[str]:
    p = PROJECT_ROOT / "config/holidays.json"
    if not p.exists():
        return set()
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return set(obj.get("holidays") or [])
    except Exception:
        return set()

def is_trading_session(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    d = now.strftime("%Y-%m-%d")
    if d in load_holidays():
        return False
    minutes = now.hour * 60 + now.minute
    return (570 <= minutes <= 690) or (780 <= minutes <= 900)

def fetch_and_save(day: str, force: bool):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在执行 M1-Market-Amount: 抓取全市场与ETF成交额")
    
    now = datetime.now()
    if not force and not is_trading_session(now):
        print("  ⏭️ 非交易时段，跳过抓取")
        return 0
    
    # 1. 抓取全市场成交额
    try:
        import akshare as ak
        df_index = ak.stock_zh_index_spot_sina()
        df_sh = df_index[df_index['代码'] == 'sh000001']
        df_sz = df_index[df_index['代码'] == 'sz399001']
        
        if df_sh.empty or df_sz.empty:
            print("  ❌ 抓取全市场成交额失败: akshare 返回空数据")
            return 1
            
        sh_amt = float(df_sh.iloc[0]['成交额'])
        sz_amt = float(df_sz.iloc[0]['成交额'])
        market_total = sh_amt + sz_amt
    except Exception as e:
        print(f"  ❌ 抓取全市场成交额异常: {e}")
        return 1

    # 2. 抓取 ETF 成交额
    try:
        import akshare as ak
        etf_df = ak.fund_etf_category_sina(symbol="ETF基金")
        etf_total = float(etf_df['成交额'].fillna(0).astype(float).sum())
    except Exception as e:
        print(f"  ❌ 抓取 ETF 成交额异常: {e}")
        return 1

    share_pct = round((etf_total / market_total) * 100, 2) if market_total > 0 else 0

    # 3. 落盘
    # 拆分为 minute 和 daily 两个文件存储
    time_str = datetime.now().strftime("%H:%M")
    record = {
        "date": day,
        "time": datetime.now().strftime("%H:%M:%S"),
        "asOf": time_str,
        "market_amount": market_total,
        "etf_amount": etf_total,
        "etf_share_pct": share_pct
    }

    # 3.1 写入当天的 minute 文件
    minute_dir = PROJECT_ROOT / "data" / "market" / "minute" / "amount"
    minute_dir.mkdir(parents=True, exist_ok=True)
    minute_file = minute_dir / f"{day}.jsonl"
    
    # 去重：如果同一分钟已经写过了，就跳过
    skip = False
    if minute_file.exists():
        with open(minute_file, 'r', encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-10:]:
                if not line.strip(): continue
                try:
                    obj = json.loads(line)
                    if obj.get('asOf') == time_str:
                        skip = True
                        break
                except:
                    pass
                    
    if not skip:
        with open(minute_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 3.2 写入/更新 daily 文件 (每天只保留最新一条)
    daily_dir = PROJECT_ROOT / "data" / "market" / "daily" / "amount"
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_file = daily_dir / "daily.jsonl"
    
    daily_records = []
    if daily_file.exists():
        with open(daily_file, 'r', encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    obj = json.loads(line)
                    if obj.get('date') != day:  # 剔除当天的老数据，只保留历史
                        daily_records.append(obj)
                except:
                    pass
                    
    daily_records.append(record)  # 把最新的当天数据加进去
    
    with open(daily_file, "w", encoding="utf-8") as f:
        for r in daily_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        
    # 写入 Meta
    meta = {
        "datasetId": "market_amount_daily",
        "providerId": "akshare.sina",
        "asOf": datetime.now().isoformat(),
        "date": day
    }
    (daily_dir / "daily.jsonl.meta.json").write_text(json.dumps(meta, indent=2))

    print(f"  ✅ 成功！全市场={market_total/1e8:.2f}亿, ETF={etf_total/1e8:.2f}亿, 占比={share_pct}%")
    return 0

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    exit(fetch_and_save(args.day, args.force))