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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="sh000001,sz399001,sz399006,sh000688,sh000300,sh000852")
    p.add_argument("--day", default="")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    now = datetime.now()
    day = args.day or now.strftime("%Y-%m-%d")
    as_of = now.strftime("%H:%M")
    if not args.force and not is_trading_session(now):
        print(json.dumps({"ok": True, "skipped": True, "reason": "not_trading_session", "day": day, "asOf": as_of}))
        return 0

    try:
        import akshare as ak
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"import_failed: {e}"}))
        return 1

    try:
        df = ak.stock_zh_index_spot_sina()
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"fetch_failed: {e}"}))
        return 1

    symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    wrote = []
    skipped = []
    for sym in symbols:
        try:
            search_sym = sym
            row = df[df["代码"] == search_sym]
            if row.empty:
                skipped.append(sym)
                continue
                
            row = row.iloc[0]
            price = float(row["最新价"])
        except Exception:
            skipped.append(sym)
            continue
        out = PROJECT_ROOT / f"data/market/minute/{sym}/{day}.jsonl"
        ok = append_jsonl(out, {"time": now.isoformat(), "asOf": as_of, "price": price})
        if ok:
            wrote.append(sym)

    print(json.dumps({"ok": True, "day": day, "asOf": as_of, "wrote": wrote, "skipped": skipped, "symbols": symbols}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

