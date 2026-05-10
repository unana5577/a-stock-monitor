import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
 
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = PROJECT_ROOT


def data_base() -> Path:
    return (DATA_ROOT / "data") if (DATA_ROOT / "data").exists() else DATA_ROOT


def data_path(*parts: str) -> Path:
    return data_base().joinpath(*parts)
 
 
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
 
 
def infer_cum_mode(values: list[float]) -> str:
    xs = [float(v) for v in values if v is not None]
    if len(xs) < 5:
        return "unknown"
    dec = 0
    total = 0
    prev = xs[0]
    for v in xs[1:]:
        total += 1
        if v < prev - 1e-6:
            dec += 1
        prev = v
    if total <= 0:
        return "unknown"
    ratio_non_dec = 1 - dec / total
    if ratio_non_dec >= 0.98 and xs[-1] >= xs[0]:
        return "cum"
    return "inc"


def get_amt_value(row: dict[str, Any]) -> float | None:
    v = safe_num(row.get("amount"))
    if v is None:
        v = safe_num(row.get("vol"))
    if v is None:
        v = safe_num(row.get("volume"))
    return float(v) if v is not None else None


def cum_value_upto(series: list[dict[str, Any]], day: str, base_t: datetime, mode: str) -> float:
    vals: list[tuple[datetime, float]] = []
    for row in series:
        hhmm = str(row.get("asOf") or "")
        t = parse_hhmm(day, hhmm)
        if not t or t > base_t:
            continue
        v = get_amt_value(row)
        if v is None:
            continue
        vals.append((t, float(v)))
    vals.sort(key=lambda x: x[0])
    if not vals:
        return 0.0
    if mode == "cum":
        offset = 0.0
        prev_adj = vals[0][1]
        for _, raw in vals:
            if raw < prev_adj * 0.5:
                offset += prev_adj
            adj = raw + offset
            if adj < prev_adj:
                adj = prev_adj
            prev_adj = adj
        return float(prev_adj)
    s = 0.0
    for _, raw in vals:
        if raw > 0:
            s += raw
    return float(s)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    n = len(xs)
    if n == 1:
        return xs[0]
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1 - w) + xs[hi] * w


def load_daily_pct_thresholds(symbol: str, lookback_days: int = 120) -> tuple[float | None, float | None]:
    p = data_path("etf", "daily", symbol, "daily.jsonl")
    if not p.exists():
        return None, None
    vals: list[float] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        v = safe_num(obj.get("pct"))
        if v is None:
            continue
        if abs(v) > 30:
            continue
        vals.append(float(v))
    if len(vals) >= lookback_days:
        vals = vals[-lookback_days:]
    p80 = percentile(vals, 0.8)
    p10 = percentile(vals, 0.1)
    return p80, p10


def load_prev_daily_amount(symbol: str, day: str) -> float | None:
    p = data_path("etf", "daily", symbol, "daily.jsonl")
    if not p.exists():
        return None
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("date"):
            rows.append(obj)
    rows.sort(key=lambda x: str(x.get("date")))
    prev = None
    for r in rows:
        if str(r.get("date")) < day:
            prev = r
    if not prev:
        return None
    v = safe_num(prev.get("amount"))
    return float(v) if v is not None else None


def load_prev_daily_volume(symbol: str, day: str) -> float | None:
    p = data_path("etf", "daily", symbol, "daily.jsonl")
    if not p.exists():
        return None
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("date"):
            rows.append(obj)
    rows.sort(key=lambda x: str(x.get("date")))
    prev = None
    for r in rows:
        if str(r.get("date")) < day:
            prev = r
    if not prev:
        return None
    v = safe_num(prev.get("vol"))
    if v is None:
        v = safe_num(prev.get("volume"))
    if v is None:
        v = safe_num(prev.get("amount"))
    return float(v) if v is not None else None


def load_prev_daily_close(symbol: str, day: str) -> float | None:
    p = data_path("etf", "daily", symbol, "daily.jsonl")
    if not p.exists():
        return None
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("date"):
            rows.append(obj)
    rows.sort(key=lambda x: str(x.get("date")))
    prev = None
    for r in rows:
        if str(r.get("date")) < day:
            prev = r
    if not prev:
        return None
    v = safe_num(prev.get("close"))
    return float(v) if v is not None else None


def trading_elapsed_minutes(hhmm: str) -> int:
    try:
        h, m = hhmm.split(":")
        mins = int(h) * 60 + int(m)
    except Exception:
        return 0
    open_m = 9 * 60 + 30
    am_close = 11 * 60 + 30
    pm_open = 13 * 60
    pm_close = 15 * 60
    if mins <= open_m:
        return 0
    if mins <= am_close:
        return mins - open_m
    if mins < pm_open:
        return 120
    if mins <= pm_close:
        return 120 + (mins - pm_open)
    return 240


def price_zone_label(pct: float, p80: float | None, p10: float | None) -> str:
    strong = p80 if p80 is not None else 2.0
    weak = p10 if p10 is not None else -2.0
    if pct > strong:
        return "强势上涨"
    if pct > 1:
        return "正常上涨"
    if -1 <= pct <= 1:
        return "横盘"
    if pct >= weak:
        return "正常下跌"
    return "极端下跌"


def zone_duration_minutes(series: list[dict[str, Any]], day: str, asof: str, zone: str, p80: float | None, p10: float | None) -> int:
    base = parse_hhmm(day, asof)
    if not base:
        return 0
    start_limit = parse_hhmm(day, "10:00")
    if start_limit and base < start_limit:
        return 0
    last_t = None
    dur = 0
    for row in reversed(series):
        hhmm = str(row.get("asOf") or "")
        t = parse_hhmm(day, hhmm)
        if not t or t > base:
            continue
        if start_limit and t < start_limit:
            break
        v = safe_num(row.get("_pct_calc") if "_pct_calc" in row else row.get("pct"))
        if v is None:
            continue
        z = price_zone_label(float(v), p80, p10)
        if z != zone:
            break
        if last_t is None:
            last_t = t
            dur = 1
        else:
            step = int((last_t - t).total_seconds() // 60)
            if step <= 0:
                continue
            dur += step
            last_t = t
        if dur >= 240:
            break
    return dur


def fund_heat_label(est_ratio: float | None) -> str:
    if est_ratio is None:
        return "平量"
    if est_ratio >= 1.5:
        return "放量"
    if est_ratio <= 0.6:
        return "缩量"
    return "平量"


def intraday_judgement(zone: str, is_persistent: bool, heat: str) -> tuple[str, str]:
    if zone == "正常下跌":
        if is_persistent and heat in ("放量", "平量"):
            return "低位承接有力", "承接有力"
        if is_persistent and heat == "缩量":
            return "缩量横盘抗跌", "洗盘中继"
        return "正常回落", "待确认"
    if zone == "极端下跌":
        if heat == "放量":
            return "放量破位", "放量破位"
        return "缩量阴跌", "流动性丧失"
    if zone == "横盘":
        if is_persistent and heat == "放量":
            return "放量横盘分歧", "多空激战"
        if is_persistent and heat == "缩量":
            return "缩量窄幅震荡", "方向未明"
        return "平盘震荡", "震荡"
    if zone == "正常上涨":
        if is_persistent:
            return "温和上涨", "主升延续"
        return "盘中拉升", "待确认"
    if zone == "强势上涨":
        if is_persistent and heat == "放量":
            return "高位放量滞涨", "警惕派发"
        if is_persistent and heat in ("缩量", "平量"):
            return "缩量强势逼空", "高位锁仓"
        if (not is_persistent) and heat == "放量":
            return "极值冲高放量", "警惕回落"
        return "盘中拉升 (待确认)", "待确认"
    return "盘中震荡", "震荡"


def intraday_reason_text(zone: str, is_persistent: bool, heat: str) -> str:
    if zone == "正常下跌":
        if is_persistent and heat in ("放量", "平量"):
            return "跌超1%但没破底线，且1小时以上跌不下去了，资金在持续接盘。"
        if is_persistent and heat == "缩量":
            return "跌超1%后横住超1小时，没人卖了，流动性干涸。"
        return "刚跌下来，还没稳住，承接不明。"
    if zone == "极端下跌":
        if heat == "放量":
            return "跌破底线且伴随巨大成交量，恐慌踩踏。"
        return "跌破底线但无量，流动性枯竭导致的阴跌。"
    if zone == "横盘":
        if is_persistent and heat == "放量":
            return "水面附近长时间僵持且巨量换手，多空激战。"
        if is_persistent and heat == "缩量":
            return "水面附近长时间僵持，没人交易，方向未明。"
        return "水面附近常规窄幅震荡。"
    if zone == "正常上涨":
        if is_persistent:
            return "温和推升且时间够长，趋势健康。"
        return "刚拉起来，还没站稳。"
    if zone == "强势上涨":
        if is_persistent and heat == "放量":
            return "涨到极值后长时间横住，且巨量换手，主力在派发。"
        if is_persistent and heat in ("缩量", "平量"):
            return "涨到极值后长时间坚挺，抛压极小，主力锁仓。"
        if (not is_persistent) and heat == "放量":
            return "瞬间拉到极值且爆量，容易冲高回落。"
        return "涨到极值附近但尚未站稳。"
    return "盘中走势未形成有效定性。"
 
 
def build_table(rows: list[dict[str, Any]]) -> str:
    headers = ["ETF", "池", "pct", "价格空间", "盘中状态", "承接/派发", "预估量比"]
    md = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        md.append(
            "| "
            + " | ".join(
                [
                    str(r.get("name") or "-"),
                    str(r.get("pool") or "-"),
                    str(r.get("pct") or "-"),
                    str(r.get("动能") or "-"),
                    str(r.get("操作建议") or "-"),
                    str(r.get("资金行为") or "-"),
                    str(r.get("热度占比") or "-"),
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
    p.add_argument("--data_root", default="")
    args = p.parse_args()
 
    day = str(args.day)
    now = datetime.now()
    asof = str(args.asof).strip() or now.strftime("%H:%M")
    interval = int(args.interval)
    global DATA_ROOT
    if str(args.data_root).strip():
        DATA_ROOT = Path(str(args.data_root)).expanduser().resolve()
 
    proxy = read_json(PROJECT_ROOT / "data/sector-proxy.json") or {}
    etf_dict = (proxy.get("variants") or {}).get("etf") or {}
    etf_meta = proxy.get("etf_meta") or {}
 
    lifecycle = read_json(data_path("lifecycle", "lifecycle.json")) or {}
    lifecycle_items = lifecycle.get("data") or []
    lifecycle_map = {str(it.get("symbol")): it for it in lifecycle_items if it.get("symbol")}
 
    base_t = parse_hhmm(day, asof)
    if not base_t:
        print(f"DEBUG: base_t parsing failed for {day} {asof}")
        return 1

    rows: list[dict[str, Any]] = []
    series_cache: dict[str, list[dict[str, Any]]] = {}

    for name, symbol in etf_dict.items():
        symbol = str(symbol)
        meta = etf_meta.get(name) or {}
        sub = meta.get("sub_category") or ""
        series_file = data_path("etf", "minute", symbol, f"{day}.jsonl")
        series = load_jsonl_all(series_file)
        series_cache[symbol] = series
        prev_close = load_prev_daily_close(symbol, day)
        if prev_close is not None and prev_close > 0:
            for row in series:
                pct_field = safe_num(row.get("pct"))
                if pct_field is not None and abs(float(pct_field)) > 1e-9:
                    row["_pct_calc"] = float(pct_field)
                    continue
                px = safe_num(row.get("price"))
                if px is None:
                    px = safe_num(row.get("close"))
                if px is None:
                    continue
                base_close = safe_num(row.get("pre_close"))
                if base_close is None or base_close <= 0:
                    base_close = float(prev_close)
                row["_pct_calc"] = (float(px) / float(base_close) - 1.0) * 100.0
        cur = pick_point_at_or_before(series, day, asof)
        if not cur:
            continue
 
        cur_t = parse_hhmm(day, str(cur.get("asOf") or ""))
        if not cur_t:
            continue
        target_t = parse_hhmm(day, asof)
        if not target_t:
            continue
        if (target_t - cur_t).total_seconds() > 10 * 60:
            continue

        pct = safe_num(cur.get("_pct_calc") if "_pct_calc" in cur else cur.get("pct"))
        if pct is None:
            continue
        pct_val = float(pct)

        p80, p10 = load_daily_pct_thresholds(symbol, 120)
        zone = price_zone_label(pct_val, p80, p10)
        dur = zone_duration_minutes(series, day, asof, zone, p80, p10)
        is_persistent = dur >= 60
        time_state = "持久" if is_persistent else "短暂"

        # amount/vol 可能来自：
        # - 新浪实时：开盘累计
        # - 盘后回补：每分钟增量
        raw_vals = []
        for row in series:
            hhmm = str(row.get("asOf") or "")
            t = parse_hhmm(day, hhmm)
            if not t or t > base_t:
                continue
            v = get_amt_value(row)
            if v is None:
                continue
            raw_vals.append(float(v))
        mode = infer_cum_mode(raw_vals)
        if mode == "unknown":
            mode = "cum"

        cur_amt = cum_value_upto(series, day, base_t, mode)
        prev_amt = load_prev_daily_amount(symbol, day)
        est_ratio = None
        if prev_amt is not None and prev_amt > 0:
            elapsed = trading_elapsed_minutes(asof)
            if elapsed > 0:
                est_amt = float(cur_amt) / (elapsed / 240.0)
                est_ratio = est_amt / float(prev_amt)
        heat = fund_heat_label(est_ratio)
        intraday_status, fund_judge = intraday_judgement(zone, is_persistent, heat)
        if fund_judge == "待确认":
            fund_judge = ""

        lci = lifecycle_map.get(symbol) or {}
        pool = "黄"
        try:
            bias = float(((lci.get("指标数据") or {}).get("Bias_20")) or 0)
            mx = float(((lci.get("指标数据") or {}).get("Bias_20_History_Max")) or 0)
            if lci.get("动能") == "强势向上" and mx != 0 and bias >= 0.9 * mx:
                pool = "红"
            elif lci.get("动能") in ("强势向上", "偏强向上"):
                pool = "绿"
        except Exception:
            pool = "黄"

        ratio_txt = f"{est_ratio:.2f}" if est_ratio is not None else "-"
        evidence = intraday_reason_text(zone, is_persistent, heat)
 
        rows.append(
            {
                "name": name,
                "symbol": symbol,
                "category": meta.get("category") or "",
                "sub_category": sub,
                "asOf": asof,
                "pct": round(pct_val, 2),
                "pool": pool,
                "操作建议": intraday_status,
                "动能": zone,
                "资金行为": f"{time_state}·{heat}",
                "热度占比": heat,
                "归因说明": evidence,
            }
        )
 
    rows.sort(key=lambda r: (safe_num(r.get("pct")) or 0.0), reverse=True)
 
    snapshot = {"date": day, "asOf": asof, "intervalMin": interval, "items": rows}
 
    if args.persist:
        out_dir = data_path("lifecycle", "intraday")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"etf_snapshot_{day}.jsonl"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
 
    print(build_table(rows))
 
    return 0
 
 
if __name__ == "__main__":
    raise SystemExit(main())
