"""
五阶段策略实时引擎 (V3)
=======================
用法:
  python3 波段策略/stage_runner.py [--day YYYY-MM-DD] [--symbols s1,s2,...] [--use-minute] [--output-snapshot]
  
  --use-minute: 盘中读取分钟线最新价拼入日线, 输出 minute_price 字段
  --output-snapshot: 将结果写入 data/stage/snapshot.json (不输出 stdout)
  
  典型调用:
    n8n 定时: python3 ... --use-minute --output-snapshot
    API 实时: python3 ... --day today (stdout, 不读分钟线)
"""
import json, os, sys, argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, DIR)

from stage_detector import (
    detect_stage,
    STAGE_RANGED, STAGE_STARTUP, STAGE_UPTREND, STAGE_DECLINING, STAGE_DEFENSE
)

DEFAULT_SYMBOLS = ["sh515880", "sh512480", "sh563530", "sh516510", "sh562500"]


def load_symbols_from_proxy():
    """从 sector-proxy.json 读取全部 ETF 代码和名称"""
    proxy_path = os.path.join(ROOT, "data", "sector-proxy.json")
    if not os.path.exists(proxy_path):
        return DEFAULT_SYMBOLS, SYMBOL_NAMES

    try:
        with open(proxy_path) as f:
            cfg = json.load(f)
        variants = cfg.get("variants", {})
        etf_map = variants.get("etf", {})
        meta = cfg.get("etf_meta", {})

        if not etf_map:
            return DEFAULT_SYMBOLS, SYMBOL_NAMES

        symbols = []
        names = {}
        for name, code in etf_map.items():
            m = meta.get(name, {})
            if not m.get("hidden"):
                symbols.append(code)
                names[code] = name

        if not symbols:
            return DEFAULT_SYMBOLS, SYMBOL_NAMES

        return symbols, names
    except Exception:
        return DEFAULT_SYMBOLS, SYMBOL_NAMES


DYNAMIC_SYMBOLS, DYNAMIC_NAMES = load_symbols_from_proxy()
SYMBOL_NAMES = {
    "sh515880": "通信ETF", "sh512480": "半导体ETF",
    "sh563530": "商业航天ETF", "sh516510": "云计算ETF",
    "sh562500": "机器人ETF"
}
STAGE_ICON = {
    STAGE_RANGED: "🔵", STAGE_STARTUP: "🟡",
    STAGE_UPTREND: "🟢", STAGE_DECLINING: "🟠", STAGE_DEFENSE: "⚫"
}


def read_daily(symbol: str) -> List[dict]:
    path = os.path.join(ROOT, "data", "etf", "daily", symbol, "daily.jsonl")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def read_minute_today(symbol: str, target_day: str) -> List[dict]:
    path = os.path.join(ROOT, "data", "etf", "minute", symbol, f"{target_day}.jsonl")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def compute_snapshot(symbol: str, target_day: str, use_minute: bool = False) -> dict:
    rows = read_daily(symbol)
    if not rows:
        return {"symbol": symbol, "error": "no data"}

    minute_price = None
    minute_pct = None
    minute_as_of = None

    if use_minute:
        minute_rows = read_minute_today(symbol, target_day)
        if minute_rows:
            latest = minute_rows[-1]
            minute_price = round(latest.get("price", 0), 4)
            minute_pct = round(latest.get("pct", 0), 2)
            minute_as_of = latest.get("asOf", latest.get("time", "")[-8:]) if latest.get("time") else ""

            live_row = {
                "date": target_day,
                "close": minute_price,
                "open": latest.get("open", minute_price),
                "high": latest.get("high", minute_price),
                "low": latest.get("low", minute_price),
                "amount": sum(m.get("amount", 0) or 0 for m in minute_rows),
                "vol": sum(m.get("vol", 0) or 0 for m in minute_rows),
                "pct": minute_pct,
            }
            rows = rows + [live_row]

    days = [r["date"] for r in rows]
    if target_day not in days:
        actual_day = days[-1] if days else target_day
        idx = len(rows) - 1
    else:
        idx = days.index(target_day)

    row = rows[idx]
    stage, diag = detect_stage(rows, idx)

    # 主线判断: 多头排列(MA20>MA60)仍成立 — 不看阶段历史,看趋势结构
    m20_val = diag.get("ma20")
    m60_val = diag.get("ma60")
    is_main_line = (m20_val is not None and m60_val is not None and m20_val > m60_val)

    last90 = rows[max(0, idx - 89):idx + 1]
    highs = [r.get("high", r["close"]) for r in last90]
    lows = [r.get("low", r["close"]) for r in last90]
    max_high = max(highs) if highs else row["close"]
    min_low = min(lows) if lows else row["close"]

    # 资金热度: 近5日 vs 近20日均成交额
    slice5 = rows[max(0, idx - 4):idx + 1]
    slice20 = rows[max(0, idx - 19):idx + 1]
    amounts5 = [r.get("amount", 0) or 0 for r in slice5]
    amounts20 = [r.get("amount", 0) or 0 for r in slice20]
    avg5 = sum(amounts5) / max(len(amounts5), 1)
    avg20 = sum(amounts20) / max(len(amounts20), 1)
    amount_ratio = round(avg5 / avg20, 2) if avg20 > 0 and avg5 > 0 else 1.0
    if amount_ratio >= 1.3:
        amount_trend = "放量进场"
    elif amount_ratio >= 0.7:
        amount_trend = "量能持平"
    else:
        amount_trend = "缩量"

    return {
        "symbol": symbol,
        "name": DYNAMIC_NAMES.get(symbol) or SYMBOL_NAMES.get(symbol, symbol),
        "date": row["date"],
        "close": round(row["close"], 4),
        "open": round(row.get("open", 0), 4),
        "pct": round(row.get("pct", 0), 2),
        "amount": round(row.get("amount", 0), 0),
        "stage": stage,
        "stage_icon": STAGE_ICON.get(stage, ""),
        "ma20": diag.get("ma20"),
        "ma60": diag.get("ma60"),
        "ma20_slope": diag.get("ma20_slope"),
        "vol_ratio": diag.get("vol_ratio"),
        "amount_trend": amount_trend,
        "amount_ratio": amount_ratio,
        "high_90d": round(max_high, 4),
        "low_90d": round(min_low, 4),
        "was_uptrend": is_main_line,
        "minute_price": minute_price,
        "minute_pct": minute_pct,
        "minute_as_of": minute_as_of,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default="today")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--use-minute", action="store_true")
    parser.add_argument("--output-snapshot", action="store_true")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = DYNAMIC_SYMBOLS

    if args.day == "today":
        tz = timezone(timedelta(hours=8))
        target_day = datetime.now(tz).strftime("%Y-%m-%d")
    else:
        target_day = args.day

    stages = {}
    for sym in symbols:
        stages[sym] = compute_snapshot(sym, target_day, use_minute=args.use_minute)

    result = {
        "day": target_day,
        "stages": stages,
        "symbol_count": len(symbols),
        "as_of": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
    }

    if args.output_snapshot:
        out_dir = os.path.join(ROOT, "data", "stage")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "snapshot.json")
        with open(out_path, "w") as f:
            json.dump(result, f, ensure_ascii=False)
        return

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
