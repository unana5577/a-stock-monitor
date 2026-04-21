import json
import os
import sys

def analyze_local_data():
    # Path to today's archive
    # Assuming today is 2026-02-09 based on the file seen
    # In a real scenario, we might find the latest file
    data_dir = "a-stock-monitor/data"
    files = [f for f in os.listdir(data_dir) if f.startswith("archive-")]
    files.sort()
    if not files:
        print("No local data found.")
        return

    latest_file = os.path.join(data_dir, files[-1])
    print(f"Reading data from {latest_file}...")

    with open(latest_file, 'r') as f:
        lines = f.readlines()

    if not lines:
        print("File is empty.")
        return

    # Parse the last line for latest status
    last_line = json.loads(lines[-1])
    # Parse the first line for opening status (or just use the trend)
    first_line = json.loads(lines[0])

    # Mapping based on server.js
    # 0: ts
    # 1: ssePrice, 2: ssePct
    # 5: gemPrice, 6: gemPct
    # 21: volume, 22: upCount, 23: downCount
    
    sse_price = last_line[1]
    sse_pct = last_line[2]
    gem_price = last_line[5]
    gem_pct = last_line[6]
    volume = last_line[21]
    up_count = last_line[22]
    down_count = last_line[23]
    
    # Analysis
    print(f"\n--- A-Share Market Analysis ({files[-1]}) ---")
    print(f"Time: {last_line[0]}")
    
    print(f"\n[Index Status]")
    print(f"Shanghai Composite: {sse_price} ({sse_pct}%)")
    print(f"ChiNext Index: {gem_price} ({gem_pct}%)")
    
    print(f"\n[Market Sentiment]")
    if up_count and down_count:
        print(f"Up: {up_count}, Down: {down_count}")
        ratio = up_count / (up_count + down_count) if (up_count + down_count) > 0 else 0
        if ratio > 0.6:
            print("Sentiment: Strong (Bullish)")
        elif ratio < 0.4:
            print("Sentiment: Weak (Bearish)")
        else:
            print("Sentiment: Neutral")
    else:
        print("Sentiment data missing.")
        
    print(f"Volume: {volume/100000000:.2f} Billion")

    # Trend Judgment
    trend = "Neutral"
    if sse_pct > 0.5 and gem_pct > 1.0:
        trend = "Bullish"
    elif sse_pct < -0.5:
        trend = "Bearish"
    
    print(f"\n[Trend Analysis]")
    print(f"Current Trend: {trend}")
    if trend == "Bullish":
        print("Description: Indices are rising, growth stocks (ChiNext) are leading.")
    elif trend == "Bearish":
        print("Description: Market is under pressure.")
    else:
        print("Description: Market is consolidating.")

    # Position Advice
    print(f"\n[Position Management Advice]")
    if trend == "Bullish":
        print("Strategy: Aggressive. Suggested Position: 60-80%.")
        print("Focus: Growth sectors, hold winners.")
    elif trend == "Bearish":
        print("Strategy: Defensive. Suggested Position: 0-30%.")
        print("Focus: Cash is king, wait for stability.")
    else:
        print("Strategy: Balanced. Suggested Position: 30-50%.")
        print("Focus: Buy low sell high in range, low risk assets.")

if __name__ == "__main__":
    analyze_local_data()
