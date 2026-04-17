import json
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def fetch_and_save(day: str):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 正在执行 M1-Market-Amount: 抓取全市场与ETF成交额")
    
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

    record = {
        "date": day,
        "time": datetime.now().strftime("%H:%M:%S"),
        "market_amount": market_total,
        "etf_amount": etf_total,
        "etf_share_pct": share_pct
    }

    # 3. 落盘
    out_dir = PROJECT_ROOT / "data" / "market"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "market_amount.jsonl"
    
    with open(out_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        
    # 写入 Meta
    meta = {
        "datasetId": "market_amount",
        "providerId": "akshare.sina",
        "asOf": datetime.now().isoformat(),
        "date": day
    }
    (out_dir / "market_amount.jsonl.meta.json").write_text(json.dumps(meta, indent=2))

    print(f"  ✅ 成功！全市场={market_total/1e8:.2f}亿, ETF={etf_total/1e8:.2f}亿, 占比={share_pct}%")
    return 0

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    args = p.parse_args()
    exit(fetch_and_save(args.day))