import akshare as ak
import pandas as pd
import datetime

def analyze_index(symbol, name):
    print(f"--- Analyzing {name} ({symbol}) ---")
    try:
        # Try fetching daily data
        # Method 1: Sina (usually stable)
        # Symbol format: sh000001
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
        except:
            df = None
        
        if df is None or df.empty:
             # Method 2: EM
             # Symbol format: usually just code "000001"
             code = symbol.replace('sh', '').replace('sz', '')
             try:
                 df = ak.stock_zh_index_daily_em(symbol=code)
             except:
                 pass
        
        if df is None or df.empty:
            print("No data found via Akshare.")
            return
        
        # Sort by date
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Get last 60 days for MA calculation
        if len(df) > 60:
            cutoff = df["date"].to_numpy()[-60]
            recent = df[df["date"] >= cutoff].copy()
        else:
            recent = df.copy()
        
        if len(recent) < 20:
            print("Not enough data for MA20.")
            return

        recent = recent.sort_values("date").reset_index(drop=True)
        records = recent.to_dict("records")
        current = records[-1]
        prev = records[-2]
        
        price = current['close']
        change_amount = price - prev['close']
        pct_change = (change_amount) / prev['close'] * 100
        
        # Calculate MAs
        recent['MA5'] = recent['close'].rolling(window=5).mean()
        recent['MA10'] = recent['close'].rolling(window=10).mean()
        recent['MA20'] = recent['close'].rolling(window=20).mean()
        
        ma5 = recent["MA5"].to_numpy()[-1]
        ma10 = recent["MA10"].to_numpy()[-1]
        ma20 = recent["MA20"].to_numpy()[-1]
        
        # Volume analysis
        # volume might be empty or 0 if real-time data hasn't updated fully, but usually daily_em has it
        vol = current.get('volume', 0)
        # Calculate MA5 Volume
        recent['VolMA5'] = recent['volume'].rolling(window=5).mean()
        vol_ma5 = recent["VolMA5"].to_numpy()[-1]
        
        vol_ratio = 0
        if vol_ma5 > 0:
            vol_ratio = vol / vol_ma5
        
        print(f"Date: {current['date'].strftime('%Y-%m-%d')}")
        print(f"Price: {price:.2f} ({pct_change:+.2f}%)")
        print(f"MA5: {ma5:.2f}")
        print(f"MA10: {ma10:.2f}")
        print(f"MA20: {ma20:.2f}")
        print(f"Volume Ratio (vs MA5 Vol): {vol_ratio:.2f}")
        
        # Trend Analysis
        trend_status = "震荡"
        if price > ma5 and ma5 > ma10 and ma10 > ma20:
            trend_status = "多头排列 (上涨)"
        elif price < ma5 and ma5 < ma10 and ma10 < ma20:
            trend_status = "空头排列 (下跌)"
        elif price > ma20:
             trend_status = "均线上方 (偏多)"
        elif price < ma20:
             trend_status = "均线下方 (偏空)"
            
        print(f"Trend: {trend_status}")
        
        # Position Advice Logic
        pos_suggestion = 0
        reason = ""
        
        if price > ma20:
            if price > ma5:
                pos_suggestion = 70
                reason = "站上MA20且在MA5之上，趋势向好，可重仓持有。"
                if vol_ratio > 1.2:
                    pos_suggestion = 80
                    reason += " 量能放大，攻击形态。"
            else:
                pos_suggestion = 50
                reason = "站上MA20但跌破MA5，短期有回调压力，中等仓位。"
        else:
            if price < ma5:
                pos_suggestion = 10
                reason = "跌破MA20且在MA5之下，趋势转弱，建议低仓或空仓观望。"
            else:
                pos_suggestion = 30
                reason = "跌破MA20但站回MA5，可能是反弹，轻仓尝试。"
                
        print(f"Suggested Position: {pos_suggestion}%")
        print(f"Reason: {reason}")
        print("")
        
    except Exception as e:
        print(f"Error analyzing {name}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_index("sh000001", "上证指数")
    analyze_index("sz399006", "创业板指")
