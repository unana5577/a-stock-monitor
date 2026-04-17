#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import akshare as ak


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class IndexLegacySpec:
    symbol: str
    name: str
    legacy_file: Path


INDEX_SPECS: list[IndexLegacySpec] = [
    IndexLegacySpec(symbol="sh000001", name="上证指数", legacy_file=PROJECT_ROOT / "data/index_daily/index_000001.jsonl"),
    IndexLegacySpec(symbol="sz399001", name="深证成指", legacy_file=PROJECT_ROOT / "data/index_daily/index_399001.jsonl"),
    IndexLegacySpec(symbol="sz399006", name="创业板指", legacy_file=PROJECT_ROOT / "data/index_daily/index_399006.jsonl"),
    IndexLegacySpec(symbol="sh000688", name="科创50", legacy_file=PROJECT_ROOT / "data/index_daily/index_000688.jsonl"),
]


def parse_legacy_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
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
    out: list[dict] = []
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
        out.append(
            {
                "date": str(d)[:10],
                "open": float(r.get("open", close_f)),
                "high": float(r.get("high", close_f)),
                "low": float(r.get("low", close_f)),
                "close": close_f,
                "pct": pct,
            }
        )
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
    missing: list[str] = []
    s = set(ds)
    cur = start
    while cur <= end:
        d = cur.isoformat()
        if cur.weekday() < 5 and d not in holidays and cur not in s:
            missing.append(d)
        cur += timedelta(days=1)
    return missing


def run_one(
    spec: IndexLegacySpec, out_root: Path, write: bool, missing_window_days: int, expect_end: str | None, apply_fix: bool = False
) -> int:
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {spec.name} ({spec.symbol})")
    rows = parse_legacy_jsonl(spec.legacy_file)
    cleaned = compute_pct(rows)

    dates = [r["date"] for r in cleaned]
    missing = iter_missing_days(dates, window_days=missing_window_days)
    tail_missing: list[str] = []
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
    print(f"  legacy: {spec.legacy_file.relative_to(PROJECT_ROOT)}")
    print(f"  records: {len(cleaned)}  range: {dates[0]} ~ {dates[-1]}")
    if missing:
        print(f"  missing(days): {len(missing)}  example: {missing[:5]}")
    else:
        print("  missing(days): 0")
    if tail_missing:
        print(f"  missing(tail): {len(tail_missing)}  days: {tail_missing}")

    if apply_fix and tail_missing:
        last_date = dates[-1]
        print(f"  [回补触发] 发现缺失，最后日期 {last_date} < 预期 {expect_end}")
        try:
            df = ak.stock_zh_index_daily_tx(symbol=spec.symbol)
            df_new = df[df['date'].astype(str) > last_date]
            
            if not df_new.empty:
                print(f"  [接口拉取] 成功获取 {len(df_new)} 条增量日线数据")
                added_dates = []
                for _, row in df_new.iterrows():
                    date_str = str(row['date'])[:10]
                    if expect_end and date_str > expect_end:
                        continue
                        
                    prev_close = cleaned[-1]["close"]
                    current_close = float(row['close'])
                    pct = (current_close - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
                    
                    new_record = {
                        "date": date_str,
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": current_close,
                        "pct": round(pct, 2)
                    }
                    cleaned.append(new_record)
                    added_dates.append(date_str)
                dates = [r["date"] for r in cleaned]
                print(f"  [合并完成] 补充日期: {', '.join(added_dates)}")
                missing = iter_missing_days(dates, window_days=missing_window_days)
            else:
                print(f"  [接口拉取] 接口返回数据中没有大于 {last_date} 的记录")
        except Exception as e:
            print(f"  [接口报错] 回补失败: {e}")

    if not write:
        return 0

    symbol_dir = out_root / spec.symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    daily_file = symbol_dir / "daily.jsonl"
    meta_file = symbol_dir / "daily.jsonl.meta.json"

    with open(daily_file, "w", encoding="utf-8") as f:
        for rec in cleaned:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    provider = "legacy:data/index_daily"
    if apply_fix and tail_missing:
        provider = "hybrid(local_legacy + akshare.tx)"

    meta = {
        "datasetId": "index_daily",
        "providerId": provider,
        "symbol": spec.symbol,
        "asOf": datetime.now().isoformat(),
        "recordCount": len(cleaned),
        "startDate": dates[0],
        "endDate": dates[-1],
        "missingDaysCount": len(missing),
    }
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ write: {daily_file.relative_to(PROJECT_ROOT)} (provider: {provider})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="all")
    p.add_argument("--out-root", default="data/m1/index")
    p.add_argument("--write", action="store_true")
    p.add_argument("--missing-window-days", type=int, default=90)
    p.add_argument("--expect-end", default=None)
    p.add_argument("--apply-fix", action="store_true")
    args = p.parse_args()

    out_root = PROJECT_ROOT / args.out_root
    specs = INDEX_SPECS if args.symbol == "all" else [s for s in INDEX_SPECS if s.symbol == args.symbol]
    if not specs:
        raise SystemExit("unknown symbol")

    for s in specs:
        run_one(
            s,
            out_root=out_root,
            write=args.write,
            missing_window_days=args.missing_window_days,
            expect_end=args.expect_end,
            apply_fix=args.apply_fix,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
