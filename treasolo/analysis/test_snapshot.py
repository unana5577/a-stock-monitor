import json
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def load_proxy_etfs():
    proxy_file = PROJECT_ROOT / "data/sector-proxy.json"
    if not proxy_file.exists():
        return {}
    with open(proxy_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    etf_dict = data.get("variants", {}).get("etf", {})
    return etf_dict

def get_p20_threshold(code):
    daily_file = PROJECT_ROOT / f"data/etf/daily/{code}/daily.jsonl"
    if not daily_file.exists():
        return None
        
    records = []
    with open(daily_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
                
    if not records:
        return None
        
    df = pd.DataFrame(records)
    df = df.tail(120).copy().reset_index(drop=True)
    df['prev_close'] = df['close'].shift(1)
    if df['pct'].iloc[0] != 0:
        df.loc[0, 'prev_close'] = df['close'].iloc[0] / (1 + df['pct'].iloc[0] / 100)
    else:
        df.loc[0, 'prev_close'] = df['close'].iloc[0]
        
    df['min_pct'] = (df['low'] - df['prev_close']) / df['prev_close'] * 100
    df = df.dropna(subset=['min_pct'])
    
    return df['min_pct'].quantile(0.2)

def analyze_snapshot(target_date="2026-04-21", target_time="11:20"):
    etfs = load_proxy_etfs()
    
    print(f"【 {target_date} {target_time} 盘中 ETF 洗盘/出货判定快照 】")
    print(f"{'ETF名称':<10} | {'日常防线(P20)':<12} | {'当时最低跌幅':<12} | {'当时最新跌幅':<12} | {'当时最高涨幅':<12} | {'盘中状态判定'}")
    print("-" * 100)
    
    for name, code in etfs.items():
        p20_line = get_p20_threshold(code)
        if p20_line is None:
            continue
            
        minute_file = PROJECT_ROOT / f"data/etf/minute/{code}/{target_date}.jsonl"
        if not minute_file.exists():
            continue
            
        records = []
        with open(minute_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
                    
        df = pd.DataFrame(records)
        # 截取到目标时间点
        df = df[df['asOf'] <= target_time]
        if df.empty:
            continue
            
        # 在该时间点之前，它曾经去过的最低点和最高点
        min_pct_so_far = df['pct'].min()
        max_pct_so_far = df['pct'].max()
        # 该时间点的最新价
        current_pct = df['pct'].iloc[-1]
        
        # 计算结构 (截至当时)
        # 用当时的最新价和开盘价的较小值，减去最低价，算下影线
        open_pct = df['pct'].iloc[0]
        min_open_close_pct = min(open_pct, current_pct)
        lower_wick_pct = min_open_close_pct - min_pct_so_far
        max_rebound = max_pct_so_far - min_pct_so_far
        
        is_deep_v = lower_wick_pct >= 0.4
        is_flat_shakeout = (max_rebound <= 3.0) and not is_deep_v
        
        status = "跌破防线(异常弱势)"
        if min_pct_so_far >= p20_line:
            if min_pct_so_far >= -0.5:
                status = "强势未砸盘(安全)"
            elif is_deep_v:
                status = "深V洗盘(拉起>0.4%)"
            elif is_flat_shakeout:
                status = "横盘洗盘(全天振幅<3.0%)"
            else:
                status = "震荡(结构未确认)"
                
        print(f"{name:<10} | {p20_line:>10.2f}%   | {min_pct_so_far:>10.2f}%   | {current_pct:>10.2f}%   | {max_pct_so_far:>10.2f}%   | {status}")

if __name__ == "__main__":
    analyze_snapshot()