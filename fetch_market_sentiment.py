#!/usr/bin/env python3
"""抓取并整理市场情绪数据。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.replace(",", "").replace("%", "").strip()
        if not s or s in {"-", "--", "nan", "None", "null"}:
            return None
        v = s
    try:
        fv = float(v)
        if pd.isna(fv):
            return None
        return fv
    except Exception:
        return None


def _normalize_date(v) -> Optional[str]:
    dt = pd.to_datetime(v, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.strftime("%Y-%m-%d")


def _pick_col(columns: Iterable[str], candidates: List[str]) -> Optional[str]:
    cols = list(columns)
    for c in candidates:
        if c in cols:
            return c
    lowered = {c.lower(): c for c in cols if isinstance(c, str)}
    for c in candidates:
        lc = c.lower()
        if lc in lowered:
            return lowered[lc]
    for c in cols:
        sc = str(c)
        for hint in candidates:
            if hint.lower() in sc.lower():
                return c
    return None


def _write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_northbound_flow(start_date: str) -> Dict:
    records: List[Dict] = []
    errors: List[str] = []

    if ak is None:
        errors.append("akshare not available")
    else:
        try:
            df = ak.stock_hsgt_hist_em(symbol="北向资金")
            if not df.empty:
                date_col = _pick_col(df.columns, ["日期", "交易日期", "TRADE_DATE", "date"])
                flow_col = _pick_col(
                    df.columns,
                    ["当日成交净买额", "当日资金流入", "净流入", "净买额", "NET_DEAL_AMT", "net_inflow"],
                )
                if date_col and flow_col:
                    for _, row in df.iterrows():
                        date_str = _normalize_date(row.get(date_col))
                        if not date_str or date_str < start_date:
                            continue
                        net_inflow = _to_float(row.get(flow_col))
                        records.append({
                            "date": date_str,
                            "net_inflow": net_inflow,
                        })
                else:
                    errors.append(f"northbound columns not found: {list(df.columns)}")
            else:
                errors.append("northbound dataframe empty")
        except Exception as e:
            errors.append(f"fetch northbound failed: {type(e).__name__}: {e}")

    dedup = {r["date"]: r for r in records}
    out = sorted(dedup.values(), key=lambda x: x["date"])
    return {
        "start_date": start_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "records": out,
        "count": len(out),
        "errors": errors,
    }


def fetch_margin_balance(start_date: str) -> Dict:
    records_by_date: Dict[str, Dict] = {}
    errors: List[str] = []

    if ak is None:
        errors.append("akshare not available")
        return {
            "start_date": start_date,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "records": [],
            "count": 0,
            "errors": errors,
        }

    sse_dates: List[str] = []
    try:
        sse_df = ak.stock_margin_sse(start_date="20010106", end_date=datetime.now().strftime("%Y%m%d"))
        if not sse_df.empty:
            date_col = _pick_col(sse_df.columns, ["信用交易日期", "日期", "交易日期", "date"])
            balance_col = _pick_col(sse_df.columns, ["融资余额", "融资余额(元)", "margin_balance"])
            if date_col and balance_col:
                for _, row in sse_df.iterrows():
                    d = _normalize_date(row.get(date_col))
                    if not d or d < start_date:
                        continue
                    val = _to_float(row.get(balance_col))
                    records_by_date.setdefault(d, {"date": d})["sse_margin_balance"] = val
                    sse_dates.append(d)
            else:
                errors.append(f"sse columns not found: {list(sse_df.columns)}")
        else:
            errors.append("sse dataframe empty")
    except Exception as e:
        errors.append(f"fetch sse margin failed: {type(e).__name__}: {e}")

    for d in sorted(set(sse_dates)):
        day_compact = d.replace("-", "")
        try:
            sz_df = ak.stock_margin_szse(date=day_compact)
            if sz_df is None or sz_df.empty:
                continue
            date_col = _pick_col(sz_df.columns, ["日期", "交易日期", "date"])
            balance_col = _pick_col(sz_df.columns, ["融资余额", "融资余额(元)", "margin_balance"])
            if not balance_col:
                errors.append(f"szse columns not found on {d}: {list(sz_df.columns)}")
                continue

            if date_col:
                match = sz_df.copy()
                match["_date"] = pd.to_datetime(match[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
                match = match[match["_date"] == d]
                v = _to_float(match[balance_col].iloc[0]) if not match.empty else None
            else:
                v = _to_float(sz_df[balance_col].iloc[0])
            if v is not None:
                records_by_date.setdefault(d, {"date": d})["szse_margin_balance"] = v
        except Exception as e:
            errors.append(f"fetch szse margin failed on {d}: {type(e).__name__}: {e}")

    records = []
    for d in sorted(records_by_date):
        item = records_by_date[d]
        sse = item.get("sse_margin_balance")
        sz = item.get("szse_margin_balance")
        item["total_margin_balance"] = (sse or 0) + (sz or 0) if (sse is not None or sz is not None) else None
        records.append(item)

    return {
        "start_date": start_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "records": records,
        "count": len(records),
        "errors": errors,
    }


def load_market_breadth_from_cache(start_date: str, data_dir: Path) -> Dict:
    records: List[Dict] = []
    errors: List[str] = []

    for p in sorted(data_dir.glob("market-breadth-*.json")):
        stem = p.stem
        token = stem.replace("market-breadth-", "")
        if len(token) != 8 or not token.isdigit():
            continue
        d = f"{token[0:4]}-{token[4:6]}-{token[6:8]}"
        if d < start_date:
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                continue
            records.append(
                {
                    "date": d,
                    "up": int(obj.get("up", 0)),
                    "down": int(obj.get("down", 0)),
                    "flat": int(obj.get("flat", 0)),
                    "total": int(obj.get("total", 0)),
                }
            )
        except Exception as e:
            errors.append(f"read breadth {p.name} failed: {type(e).__name__}: {e}")

    dedup = {r["date"]: r for r in records}
    out = sorted(dedup.values(), key=lambda x: x["date"])
    return {
        "start_date": start_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "records": out,
        "count": len(out),
        "errors": errors,
        "source": "local market-breadth-YYYYMMDD.json",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取市场情绪数据（北向/融资/涨跌家数）")
    parser.add_argument("--start-date", default="2025-05-19", help="起始日期，格式 YYYY-MM-DD")
    parser.add_argument("--data-dir", default="data", help="输出目录")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    start_date = args.start_date

    northbound = fetch_northbound_flow(start_date)
    margin = fetch_margin_balance(start_date)
    breadth = load_market_breadth_from_cache(start_date, data_dir)

    _write_json(data_dir / "northbound_flow.json", northbound)
    _write_json(data_dir / "margin_balance.json", margin)
    _write_json(data_dir / "market_breadth.json", breadth)

    print(json.dumps({
        "northbound_flow": {"count": northbound["count"], "errors": len(northbound.get("errors", []))},
        "margin_balance": {"count": margin["count"], "errors": len(margin.get("errors", []))},
        "market_breadth": {"count": breadth["count"], "errors": len(breadth.get("errors", []))},
        "start_date": start_date,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
