import json
import numpy as np
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_proxy_etfs():
    proxy_file = PROJECT_ROOT / "data/sector-proxy.json"
    if not proxy_file.exists():
        return {}
    with open(proxy_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    etf_dict = data.get("variants", {}).get("etf", {})
    etf_meta = data.get("etf_meta", {})
    
    result = {}
    for name, code in etf_dict.items():
        result[code] = {
            "name": name,
            "category": etf_meta.get(name, {}).get("category", "未知"),
            "sub_category": etf_meta.get(name, {}).get("sub_category", "未知")
        }
    return result

def calc_daily_thresholds(days_limit=250):
    etfs = load_proxy_etfs()
    results = []

    for code, meta in etfs.items():
        daily_file = PROJECT_ROOT / f"data/etf/daily/{code}/daily.jsonl"
        if not daily_file.exists():
            continue
            
        records = []
        with open(daily_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
                    
        if not records:
            continue
            
        df = pd.DataFrame(records)
        df = df.tail(days_limit).copy()
        
        # Calculate previous close for calculations
        df['prev_close'] = df['close'].shift(1)
        # For the first row, estimate prev_close using pct
        df.loc[df.index[0], 'prev_close'] = df['close'].iloc[0] / (1 + df['pct'].iloc[0] / 100) if df['pct'].iloc[0] != 0 else df['close'].iloc[0]
        
        # Drop rows with 0 prev_close to avoid division by zero
        df = df[df['prev_close'] > 0]
        
        # Calculate features
        df['amp_pct'] = (df['high'] - df['low']) / df['prev_close'] * 100
        df['upper_wick_pct'] = (df['high'] - df[['open', 'close']].max(axis=1)) / df['prev_close'] * 100
        df['lower_wick_pct'] = (df[['open', 'close']].min(axis=1) - df['low']) / df['prev_close'] * 100
        
        # Calculate percentiles
        res = {
            "ETF": meta["name"],
            "二级": meta["sub_category"],
            "样本天数": len(df),
            "max_pct_p80": round(np.percentile(df['pct'], 80), 2),
            "max_pct_p90": round(np.percentile(df['pct'], 90), 2),
            "min_pct_p20": round(np.percentile(df['pct'], 20), 2),
            "min_pct_p10": round(np.percentile(df['pct'], 10), 2),
            "amp_p80": round(np.percentile(df['amp_pct'], 80), 2),
            "upper_wick_p80": round(np.percentile(df['upper_wick_pct'], 80), 2),
            "lower_wick_p80": round(np.percentile(df['lower_wick_pct'], 80), 2),
        }
        results.append(res)
        
    return results

def print_markdown_table(results):
    if not results:
        print("没有足够的数据。")
        return
        
    headers = list(results[0].keys())
    
    # Print header
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    
    print(header_line)
    print(separator_line)
    
    # Print rows
    for row in results:
        row_line = "| " + " | ".join([str(row[h]) for h in headers]) + " |"
        print(row_line)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=250, help="回测的历史天数")
    args = parser.parse_args()
    
    print(f"正在基于近 {args.days} 个交易日的日线数据测算阈值...\n")
    results = calc_daily_thresholds(args.days)
    print_markdown_table(results)
