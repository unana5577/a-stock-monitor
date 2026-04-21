
import akshare as ak
import pandas as pd
import json

def fetch_daily(symbol):
    try:
        # Try EM source
        df = ak.stock_zh_index_daily_em(symbol=symbol)
        # Filter for 2026-02-12 and 2026-02-13
        df['date'] = pd.to_datetime(df['date'])
        mask = (df['date'] >= pd.to_datetime('2026-02-12')) & (df['date'] <= pd.to_datetime('2026-02-13'))
        filtered = df.loc[mask]
        print(f"{symbol} columns: {filtered.columns}")
        if 'amount' in filtered.columns:
             return filtered[['date', 'amount']].to_dict('records')
        return []
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return []

print("Fetching SH000001...")
sh = fetch_daily("sh000001")
print("Fetching SZ399106...")
sz = fetch_daily("sz399106")

print("SH:", sh)
print("SZ:", sz)

# Calculate totals
v12 = 0
v13 = 0

for d in sh:
    ts = pd.to_datetime(d['date']).strftime('%Y-%m-%d')
    if ts == '2026-02-12':
        v12 += d.get('amount', d.get('volume', 0))
    elif ts == '2026-02-13':
        v13 += d.get('amount', d.get('volume', 0))

for d in sz:
    ts = pd.to_datetime(d['date']).strftime('%Y-%m-%d')
    if ts == '2026-02-12':
        v12 += d.get('amount', d.get('volume', 0))
    elif ts == '2026-02-13':
        v13 += d.get('amount', d.get('volume', 0))

print(f"Total 12th: {v12}")
print(f"Total 13th: {v13}")
print(f"Delta: {v13 - v12}")
if v12 > 0:
    print(f"Pct: {(v13 - v12) / v12 * 100:.2f}%")
