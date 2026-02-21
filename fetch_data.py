import akshare as ak
import sys
import json
import pandas as pd
from datetime import datetime

# Usage: python3 fetch_data.py <symbol> <date>
# symbol examples: sh000001, 881155, TL2603
# date: 2026-02-06

def format_df(df, day):
    # Ensure columns are standard
    # Expected: time, open, close
    # Akshare usually returns: "时间", "开盘", "收盘" etc.
    res = []
    if df is None or df.empty:
        return res
        
    # Standardize column names
    col_map = {
        '时间': 'time', '开盘': 'open', '收盘': 'close',
        'day': 'time', 'open': 'open', 'close': 'close'
    }
    df = df.rename(columns=col_map)
    
    # Filter for target day
    target_str = day.replace('-', '') # 20260206
    target_dash = day # 2026-02-06
    
    for _, row in df.iterrows():
        t_str = str(row['time'])
        # Check if time matches day
        if target_str in t_str or target_dash in t_str:
            # Format time to "YYYY-MM-DD HH:MM"
            # If input is "2026-02-06 09:30:00", keep up to minutes
            t_fmt = t_str
            if len(t_str) >= 16:
                t_fmt = t_str[:16]
            res.append({
                'time': t_fmt,
                'open': float(row['open']),
                'close': float(row['close'])
            })
    return res

def fetch_bond(symbol):
    # Gov Bond futures or spot
    # TL2603 -> 30 year futures
    # T2603 -> 10 year futures
    try:
        # Akshare interface for bond futures minute data
        # symbol needs to be specific like 'TL2603'
        df = ak.futures_zh_minute_sina(symbol=symbol, period='1')
        return df
    except:
        return None

def fetch_stock_index(symbol):
    # sh000001 -> 000001
    code = symbol.replace('sh', '').replace('sz', '')
    try:
        # Eastmoney minute data via akshare
        df = ak.stock_zh_a_hist_min_em(symbol=code, period='1', adjust='')
        return df
    except:
        return None

def fetch_sector(symbol):
    # 881155 -> Bank
    try:
        # Eastmoney sector minute
        df = ak.stock_board_concept_hist_min_em(symbol=symbol, period='1')
        return df
    except:
        return None

def main():
    if len(sys.argv) < 3:
        print("[]")
        return

    symbol = sys.argv[1]
    day = sys.argv[2]
    
    df = None
    
    # Routing based on symbol pattern
    if symbol.startswith('TL') or symbol.startswith('T2') or symbol.startswith('TF'):
        df = fetch_bond(symbol)
    elif symbol.startswith('88') or symbol.startswith('BK'):
        df = fetch_sector(symbol)
    else:
        df = fetch_stock_index(symbol)
        
    data = format_df(df, day)
    print(json.dumps(data))

if __name__ == '__main__':
    main()
