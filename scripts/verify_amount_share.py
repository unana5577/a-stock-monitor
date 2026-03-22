import csv
import json
import os
import sys
from collections import defaultdict


def _num(v):
    try:
        x = float(v)
        return 0.0 if x != x else x
    except:
        return 0.0


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(root, "data", "sector-cache.csv")
    market_path = os.path.join(root, "data", "market", "market-amount-daily.jsonl")
    if not os.path.exists(cache_path) or not os.path.exists(market_path):
        print(json.dumps({"ok": False, "error": "missing_files"}, ensure_ascii=False))
        return 2
    market = {}
    with open(market_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                arr = json.loads(s)
            except:
                continue
            if not isinstance(arr, list) or len(arr) < 2:
                continue
            d = str(arr[0] or "").strip()
            a = _num(arr[1])
            if d and a > 0:
                market[d] = a
    if not market:
        print(json.dumps({"ok": False, "error": "no_market_rows"}, ensure_ascii=False))
        return 2
    by_date = defaultdict(list)
    with open(cache_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("type") or "") != "sector":
                continue
            d = str(row.get("date") or "").strip()
            if not d or d not in market:
                continue
            amt = _num(row.get("amount"))
            if amt <= 0:
                continue
            name = str(row.get("sector") or "").strip()
            if name:
                by_date[d].append((name, amt))
    if not by_date:
        print(json.dumps({"ok": False, "error": "no_common_date"}, ensure_ascii=False))
        return 2
    day = sorted(by_date.keys())[-1]
    total = market.get(day) or 0.0
    rows = by_date.get(day) or []
    rows.sort(key=lambda x: x[1], reverse=True)
    top = []
    mx = 0.0
    for name, amt in rows[:10]:
        share = 0.0 if total <= 0 else amt / total
        if share > mx:
            mx = share
        top.append({"name": name, "amount": amt, "share": share})
    print(json.dumps({"ok": True, "day": day, "market_amount": total, "max_share": mx, "top": top}, ensure_ascii=False))
    return 1 if mx > 1.5 else 0


if __name__ == "__main__":
    raise SystemExit(main())
