#!/usr/bin/env python3
import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import akshare as ak


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 核心宽基指数与 ETF 列表
INDEX_SYMBOLS = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
    "sh000300": "沪深300",
    "sh000852": "中证1000",
}

ETF_SYMBOLS = {
    "sh511130": "30年国债ETF",
    "sh511260": "10年国债ETF",
    "sh512480": "半导体ETF"
}

def parse_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        raise FileNotFoundError(str(path))
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        rows.append(json.loads(s))
    rows.sort(key=lambda r: r.get("date", ""))
    return rows

def compute_pct(rows: list[dict]) -> list[dict]:
    out = []
    prev_close = None
    for r in rows:
        d = r.get("date")
        close = r.get("close")
        if d is None or close is None:
            continue
        close_f = float(close)
        if prev_close is None or prev_close == 0:
            pct = 0.0
        else:
            pct = round((close_f / prev_close - 1) * 100, 2)
        
        # 对于 ETF，可能底表自带 amount / vol 等额外字段，尽量保留
        rec = {
            "date": str(d)[:10],
            "open": float(r.get("open", close_f)),
            "high": float(r.get("high", close_f)),
            "low": float(r.get("low", close_f)),
            "close": close_f,
            "pct": pct,
        }
        if "amount" in r:
            rec["amount"] = float(r["amount"])
        if "vol" in r:
            rec["vol"] = float(r["vol"])
            
        out.append(rec)
        prev_close = close_f
    return out

def load_holidays() -> set[str]:
    p = PROJECT_ROOT / "config/holidays.json"
    if not p.exists():
        return set()
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return set(obj.get("holidays") or [])
    except Exception:
        return set()

def iter_missing_days(dates: Iterable[str], window_days: int) -> list[str]:
    ds = sorted({date.fromisoformat(x) for x in dates if x})
    if not ds:
        return []
    holidays = load_holidays()
    end = ds[-1]
    start = max(ds[0], end - timedelta(days=window_days))
    missing = []
    s = set(ds)
    cur = start
    while cur <= end:
        d = cur.isoformat()
        if cur.weekday() < 5 and d not in holidays and cur not in s:
            missing.append(d)
        cur += timedelta(days=1)
    return missing

def fetch_index_incremental(symbol: str, last_date: str) -> list[dict]:
    df = ak.stock_zh_index_daily_tx(symbol=symbol)
    df_new = df[df['date'].astype(str) > last_date]
    records = []
    for _, row in df_new.iterrows():
        records.append({
            "date": str(row['date'])[:10],
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close']),
            "amount": float(row.get('amount', 0)),
            "vol": float(row.get('volume', 0))
        })
    return records

def fetch_etf_incremental(symbol: str, last_date: str) -> list[dict]:
    # sina 的 ETF 历史接口比较稳定
    df = ak.fund_etf_hist_sina(symbol=symbol)
    df_new = df[df['date'].astype(str) > last_date]
    records = []
    for _, row in df_new.iterrows():
        records.append({
            "date": str(row['date'])[:10],
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close']),
            "amount": float(row.get('amount', 0)),
            "vol": float(row.get('volume', 0))
        })
    return records

def run_one(symbol: str, write: bool, missing_window_days: int, expect_end: str | None, apply_fix: bool = False) -> int:
    is_index = symbol in INDEX_SYMBOLS
    is_etf = symbol in ETF_SYMBOLS
    
    if is_index:
        name = INDEX_SYMBOLS[symbol]
        out_root = PROJECT_ROOT / "data/index/daily"
    elif is_etf:
        name = ETF_SYMBOLS[symbol]
        out_root = PROJECT_ROOT / "data/etf/daily"
    else:
        # 如果是新增的没有配置的 ETF，自动按照前缀判断
        if symbol.startswith("sh5") or symbol.startswith("sz1"):
            is_etf = True
            name = f"未知ETF({symbol})"
            out_root = PROJECT_ROOT / "data/etf/daily"
        else:
            print(f"⚠️ 未知的 symbol 类型: {symbol}")
            return 1

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {name} ({symbol})")
    
    symbol_dir = out_root / symbol
    daily_file = symbol_dir / "daily.jsonl"
    
    # 1. 强制只读取标准 M1 目录下的 daily.jsonl
    # 旧目录兜底逻辑已在此版本删除，确保路径绝对纯净
    try:
        rows = parse_jsonl(daily_file)
        print(f"  [读取底表] 成功加载 {daily_file.relative_to(PROJECT_ROOT)}")
    except FileNotFoundError:
        print(f"  ⚠️ 无任何底表 ({daily_file})，准备全量初始化...")
        rows = []
            
    cleaned = compute_pct(rows)
    dates = [r["date"] for r in cleaned]
    
    if not dates:
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        missing = [start_date]
        tail_missing = [start_date]
        print(f"  ⚠️ 触发全量初始化，从 {start_date} 开始抓取")
    else:
        missing = iter_missing_days(dates, window_days=missing_window_days)
        tail_missing = []
        if expect_end:
            end_d = date.fromisoformat(dates[-1])
            exp_d = date.fromisoformat(expect_end)
            if end_d < exp_d:
                holidays = load_holidays()
                cur = end_d + timedelta(days=1)
                while cur <= exp_d:
                    d = cur.isoformat()
                    if cur.weekday() < 5 and d not in holidays:
                        tail_missing.append(d)
                    cur += timedelta(days=1)

    if dates:
        print(f"  records: {len(cleaned)}  range: {dates[0]} ~ {dates[-1]}")
    if tail_missing:
        print(f"  missing(tail): {len(tail_missing)}  days: {tail_missing}")

    if apply_fix and tail_missing:
        last_date = dates[-1] if dates else "1970-01-01"
        print(f"  [回补触发] 发现缺失，最后日期 {last_date} < 预期 {expect_end}")
        try:
            if is_index:
                new_records = fetch_index_incremental(symbol, last_date)
            else:
                new_records = fetch_etf_incremental(symbol, last_date)
                
            if new_records:
                print(f"  [接口拉取] 成功获取 {len(new_records)} 条增量日线数据")
                added_dates = []
                for row in new_records:
                    date_str = row['date']
                    if expect_end and date_str > expect_end:
                        continue
                        
                    prev_close = cleaned[-1]["close"] if cleaned else row['open']
                    current_close = row['close']
                    pct = (current_close - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
                    
                    row['pct'] = round(pct, 2)
                    cleaned.append(row)
                    added_dates.append(date_str)
                    
                dates = [r["date"] for r in cleaned]
                print(f"  [合并完成] {name}({symbol}) 补充日期: {', '.join(added_dates)}")
                missing = iter_missing_days(dates, window_days=missing_window_days)
            else:
                print(f"  [接口拉取] 接口返回数据中没有大于 {last_date} 的记录")
        except Exception as e:
            print(f"  [接口报错] 回补失败: {e}")

    if not write:
        return 0

    symbol_dir.mkdir(parents=True, exist_ok=True)
    meta_file = symbol_dir / "daily.jsonl.meta.json"

    with open(daily_file, "w", encoding="utf-8") as f:
        for rec in cleaned:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    meta = {
        "datasetId": "index_daily" if is_index else "etf_daily",
        "providerId": "backfill(akshare)",
        "symbol": symbol,
        "asOf": datetime.now().isoformat(),
        "recordCount": len(cleaned),
        "missingDays": missing,
        "expectEnd": expect_end,
    }
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--missing-window-days", type=int, default=30)
    p.add_argument("--expect-end", type=str, default="")
    p.add_argument("--apply-fix", action="store_true")
    p.add_argument("--write", action="store_true")
    args = p.parse_args()

    expect_end = args.expect_end
    if not expect_end:
        now = datetime.now()
        expect_end = now.strftime("%Y-%m-%d")

    return run_one(
        symbol=args.symbol,
        write=args.write,
        missing_window_days=args.missing_window_days,
        expect_end=expect_end,
        apply_fix=args.apply_fix,
    )


if __name__ == "__main__":
    raise SystemExit(main())
