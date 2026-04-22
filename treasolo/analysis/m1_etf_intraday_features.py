import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
 
PROJECT_ROOT = Path(__file__).resolve().parent.parent
 
 
def load_jsonl_all(p: Path) -> list[dict[str, Any]]:
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
 
 
def load_json_last(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        for line in reversed(p.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            return json.loads(line)
    except Exception:
        return None
    return None
 
 
def read_json(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
 
 
def parse_hhmm(day: str, hhmm: str) -> datetime | None:
    try:
        return datetime.strptime(f"{day} {hhmm}", "%Y-%m-%d %H:%M")
    except Exception:
        return None
 
 
def pick_point_at_or_before(series: list[dict[str, Any]], day: str, target_hhmm: str) -> dict[str, Any] | None:
    t = parse_hhmm(day, target_hhmm)
    if not t:
        return None
    best = None
    best_t = None
    for row in series:
        hhmm = str(row.get("asOf") or "")
        cur_t = parse_hhmm(day, hhmm)
        if not cur_t:
            continue
        if cur_t <= t and (best_t is None or cur_t > best_t):
            best = row
            best_t = cur_t
    return best
 
 
def safe_num(x: Any) -> float | None:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None
 
 
def action_signal(pct_delta_5m: float | None, share_delta_bp_5m: float | None) -> str:
    if pct_delta_5m is None or share_delta_bp_5m is None:
        return "未知"
    if pct_delta_5m >= 0.15 and share_delta_bp_5m >= 1:
        return "放量上攻"
    if pct_delta_5m <= -0.15 and share_delta_bp_5m <= -1:
        return "缩量回踩(洗盘)"
    if pct_delta_5m <= -0.15 and share_delta_bp_5m >= 1:
        return "放量下跌(出货)"
    if pct_delta_5m >= 0.15 and share_delta_bp_5m <= -1:
        return "缩量拉升"
    return "震荡"
 
 
def corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 5:
        return None
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(vx * vy)
 
 
def build_table(rows: list[dict[str, Any]]) -> str:
    headers = ["ETF", "二级", "pct", "Δpct(5m)", "share%", "Δshare(bp)", "量价", "底色"]
    md = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        md.append(
            "| "
            + " | ".join(
                [
                    str(r.get("name") or "-"),
                    str(r.get("sub_category") or "-"),
                    str(r.get("pct") or "-"),
                    str(r.get("pct_delta_5m") or "-"),
                    str(r.get("amount_share_pct") or "-"),
                    str(r.get("amount_share_delta_bp_5m") or "-"),
                    str(r.get("action") or "-"),
                    str(r.get("trend_phase") or "-"),
                ]
            )
            + " |"
        )
    return "\n".join(md)
 
 
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--day", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--asof", default="")
    p.add_argument("--interval", type=int, default=5)
    p.add_argument("--persist", action="store_true")
    args = p.parse_args()
 
    day = str(args.day)
    now = datetime.now()
    asof = str(args.asof).strip() or now.strftime("%H:%M")
    interval = int(args.interval)
 
    proxy = read_json(PROJECT_ROOT / "data/sector-proxy.json") or {}
    etf_dict = (proxy.get("variants") or {}).get("etf") or {}
    etf_meta = proxy.get("etf_meta") or {}
 
    lifecycle = read_json(PROJECT_ROOT / "data/lifecycle/lifecycle.json") or {}
    lifecycle_items = lifecycle.get("data") or []
    lifecycle_map = {str(it.get("symbol")): it for it in lifecycle_items if it.get("symbol")}
 
    market_amount = load_json_last(PROJECT_ROOT / f"data/market/minute/amount/{day}.jsonl") or {}
    market_amount_v = safe_num(market_amount.get("market_amount")) or 0.0
 
    base_t = parse_hhmm(day, asof)
    if not base_t:
        return 1
    prev_t = base_t - timedelta(minutes=interval)
    prev_hhmm = prev_t.strftime("%H:%M")
 
    rows: list[dict[str, Any]] = []
    series_cache: dict[str, list[dict[str, Any]]] = {}
 
    for name, symbol in etf_dict.items():
        symbol = str(symbol)
        meta = etf_meta.get(name) or {}
        sub = meta.get("sub_category") or ""
        series = load_jsonl_all(PROJECT_ROOT / f"data/etf/minute/{symbol}/{day}.jsonl")
        series_cache[symbol] = series
 
        cur = pick_point_at_or_before(series, day, asof)
        prev = pick_point_at_or_before(series, day, prev_hhmm)
        if not cur:
            continue
 
        pct = safe_num(cur.get("pct"))
        prev_pct = safe_num(prev.get("pct")) if prev else None
        pct_delta = round((pct - prev_pct), 2) if pct is not None and prev_pct is not None else None
 
        amt = safe_num(cur.get("amount"))
        prev_amt = safe_num(prev.get("amount")) if prev else None
 
        share = (amt / market_amount_v) if amt is not None and market_amount_v > 0 else None
        prev_share = (prev_amt / market_amount_v) if prev_amt is not None and market_amount_v > 0 else None
 
        share_pct = round((share * 100), 3) if share is not None else None
        share_delta_bp = round(((share - prev_share) * 10000), 2) if share is not None and prev_share is not None else None
 
        lci = lifecycle_map.get(symbol) or {}
        trend_phase = lci.get("位置名称") or lci.get("阶段信号") or lci.get("位置区域") or ""
 
        rows.append(
            {
                "name": name,
                "symbol": symbol,
                "category": meta.get("category") or "",
                "sub_category": sub,
                "asOf": asof,
                "pct": round(pct, 2) if pct is not None else None,
                "pct_delta_5m": pct_delta,
                "amount_share_pct": share_pct,
                "amount_share_delta_bp_5m": share_delta_bp,
                "action": action_signal(pct_delta, share_delta_bp),
                "trend_phase": trend_phase,
            }
        )
 
    rows.sort(key=lambda r: (safe_num(r.get("pct")) or 0.0), reverse=True)
 
    snapshot = {"date": day, "asOf": asof, "intervalMin": interval, "market_amount": market_amount_v, "items": rows}
 
    if args.persist:
        out_dir = PROJECT_ROOT / "data/lifecycle/intraday"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"etf_snapshot_{day}.jsonl"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
 
    print(build_table(rows))
 
    symbols = [r["symbol"] for r in rows]
    changes: dict[str, list[float]] = {}
    for sym in symbols:
        series = series_cache.get(sym) or []
        pts: list[tuple[datetime, float]] = []
        for row in series:
            hhmm = str(row.get("asOf") or "")
            t = parse_hhmm(day, hhmm)
            v = safe_num(row.get("pct"))
            if t and v is not None:
                pts.append((t, v))
        pts.sort(key=lambda x: x[0])
        if not pts:
            continue
        window_start = base_t - timedelta(minutes=30)
        w = [(t, v) for t, v in pts if window_start <= t <= base_t]
        if len(w) < 6:
            continue
        buckets: dict[int, float] = {}
        for t, v in w:
            k = int((t - window_start).total_seconds() // (interval * 60))
            buckets[k] = v
        ks = sorted(buckets.keys())
        seq = [buckets[k] for k in ks]
        deltas = [seq[i] - seq[i - 1] for i in range(1, len(seq))]
        if len(deltas) >= 5:
            changes[sym] = deltas[-8:]
 
    pairs: list[tuple[float, str, str]] = []
    syms = list(changes.keys())
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = syms[i], syms[j]
            xs = changes[a]
            ys = changes[b]
            n = min(len(xs), len(ys))
            if n < 5:
                continue
            v = corr(xs[-n:], ys[-n:])
            if v is None:
                continue
            pairs.append((v, a, b))
 
    pairs.sort(key=lambda x: x[0])
    top = [p for p in pairs if p[0] <= -0.6][:3]
    if top:
        print("")
        print("| 跷跷板候选 | A | B | corr |")
        print("| --- | --- | --- | --- |")
        name_by_sym = {r["symbol"]: f'{r["sub_category"]}-{r["name"]}' for r in rows}
        for v, a, b in top:
            print(f'| yes | {name_by_sym.get(a, a)} | {name_by_sym.get(b, b)} | {v:.2f} |')
    else:
        print("")
        print("| 跷跷板候选 | 结论 |")
        print("| --- | --- |")
        print("| no | 未见明显跷跷板（近30分钟反相关不足） |")
 
    return 0
 
 
if __name__ == "__main__":
    raise SystemExit(main())
