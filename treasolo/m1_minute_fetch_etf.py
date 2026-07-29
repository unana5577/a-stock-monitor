import argparse
import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_holidays() -> set[str]:
    p = PROJECT_ROOT / "config/holidays.json"
    if not p.exists():
        return set()
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return set(obj.get("holidays") or [])
    except Exception:
        return set()


def is_trading_session(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    d = now.strftime("%Y-%m-%d")
    if d in load_holidays():
        return False
    minutes = now.hour * 60 + now.minute
    return (570 <= minutes <= 690) or (780 <= minutes <= 900)


def append_jsonl(path: Path, record: dict) -> bool:
    if path.exists():
        try:
            last = path.read_text(encoding="utf-8").splitlines()[-1].strip()
            if last:
                obj = json.loads(last)
                if obj.get("asOf") == record.get("asOf"):
                    return False
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def fetch_eastmoney_minute(sym: str, day: str) -> list[dict]:
    import urllib.request, ssl
    code = sym[2:]
    market = "1" if sym.startswith("sh") else "0"
    secid = f"{market}.{code}"
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2&fields2=f51,f52,f53,f54,f55,f56,f57"
        f"&klt=1&fqt=1&end=20500101&lmt=300"
    )
    ctx = ssl.create_default_context()
    ctx.set_ciphers('DEFAULT')
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "*/*"
    })
    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
    data = json.loads(resp.read())
    klines = (data.get("data") or {}).get("klines") or []
    records = []
    pre_close = None
    for bar in klines:
        parts = bar.split(",")
        bar_day = parts[0].split(" ")[0]
        if bar_day != day:
            continue
        bar_time = parts[0].split(" ")[1][:5] if " " in parts[0] else parts[0][-5:]
        op = float(parts[1])
        close = float(parts[2])
        high = float(parts[3])
        low = float(parts[4])
        vol = float(parts[5]) * 100
        amt_raw = float(parts[6]) if len(parts) > 6 and parts[6] else 0
        amount = amt_raw if amt_raw > 0 else close * vol
        if pre_close is None:
            pre_close = op
        pct = round((close - pre_close) / pre_close * 100, 3) if pre_close and pre_close > 0 else 0
        records.append({
            "time": f"{day}T{bar_time}:00",
            "asOf": bar_time,
            "price": close,
            "pct": pct,
            "amount": round(amount, 2),
            "vol": int(vol),
            "open": op,
            "high": high,
            "low": low,
            "pre_close": pre_close,
        })
    return records


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="")
    p.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--force", action="store_true")
    p.add_argument("--backfill", action="store_true")
    args = p.parse_args()

    now = datetime.now()
    day = args.day or now.strftime("%Y-%m-%d")
    as_of = now.strftime("%H:%M")

    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]

    if args.backfill and symbols:
        wrote = []
        failed = []
        for sym in symbols:
            try:
                records = fetch_eastmoney_minute(sym, day)
                if not records:
                    failed.append(sym)
                    continue
                out = PROJECT_ROOT / f"data/etf/minute/{sym}/{day}.jsonl"
                out.parent.mkdir(parents=True, exist_ok=True)
                with open(out, "w", encoding="utf-8") as f:
                    for rec in records:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                wrote.append(sym)
            except Exception:
                failed.append(sym)
        print(json.dumps({
            "ok": True, "day": day, "asOf": as_of,
            "wrote": wrote, "skipped": failed, "symbols": symbols,
            "mode": "backfill"
        }, ensure_ascii=False))
        return 0

    if not args.force and not is_trading_session(now):
        print(json.dumps({"ok": True, "skipped": True, "reason": "not_trading_session", "day": day, "asOf": as_of}))
        return 0

    if not symbols:
        print(json.dumps({"ok": True, "skipped": True, "reason": "empty_symbols", "day": day, "asOf": as_of}))
        return 0

    try:
        import akshare as ak
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"import_failed: {e}"}))
        return 1

    try:
        df = ak.fund_etf_category_sina(symbol="ETF基金")
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"fetch_failed: {e}"}))
        return 1

    wrote = []
    skipped = []

    for sym in symbols:
        try:
            row = df[df["代码"] == sym]
            if row.empty:
                skipped.append(sym)
                continue

            row = row.iloc[0]
            record = {
                "time": now.isoformat(),
                "asOf": as_of,
                "price": float(row["最新价"]),
                "pct": float(row["涨跌幅"]),
                "amount": float(row["成交额"]),
                "vol": float(row["成交量"]),
                "open": float(row["今开"]),
                "high": float(row["最高"]),
                "low": float(row["最低"]),
                "pre_close": float(row["昨收"])
            }
        except Exception:
            skipped.append(sym)
            continue

        out = PROJECT_ROOT / f"data/etf/minute/{sym}/{day}.jsonl"
        ok = append_jsonl(out, record)
        if ok:
            wrote.append(sym)

    print(json.dumps({
        "ok": True,
        "day": day,
        "asOf": as_of,
        "wrote": wrote,
        "skipped": skipped,
        "symbols": symbols,
        "mode": "live"
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
