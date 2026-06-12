"""
五阶段策略实时引擎 (V2)
=======================
被 server.js 通过 execFile 调用, 计算指定日每只ETF的阶段 + V2校准数据。

用法: python3 波段策略/stage_runner.py [--day YYYY-MM-DD] [--symbols s1,s2,...]
输出: JSON (stdout)
"""
import json, os, sys, argparse
from typing import Dict, List

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, DIR)

from stage_detector import (
    detect_stage,
    STAGE_RANGED, STAGE_STARTUP, STAGE_UPTREND, STAGE_DECLINING, STAGE_DEFENSE
)

DEFAULT_SYMBOLS = ["sh515880", "sh512480", "sh563530", "sh516510", "sh562500"]
SYMBOL_NAMES = {
    "sh515880": "通信ETF", "sh512480": "半导体ETF",
    "sh563530": "商业航天ETF", "sh516510": "云计算ETF",
    "sh562500": "机器人ETF"
}
STAGE_ICON = {
    STAGE_RANGED: "🔵", STAGE_STARTUP: "🟡",
    STAGE_UPTREND: "🟢", STAGE_DECLINING: "🟠", STAGE_DEFENSE: "🔴"
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


def compute_snapshot(symbol: str, target_day: str) -> dict:
    rows = read_daily(symbol)
    if not rows:
        return {"symbol": symbol, "error": "no data"}

    days = [r["date"] for r in rows]
    if target_day not in days:
        actual_day = days[-1] if days else target_day
        idx = len(rows) - 1
    else:
        idx = days.index(target_day)

    row = rows[idx]
    stage, diag = detect_stage(rows, idx)

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
        "name": SYMBOL_NAMES.get(symbol, symbol),
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
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default="today")
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = DEFAULT_SYMBOLS

    if args.day == "today":
        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=8))
        target_day = datetime.now(tz).strftime("%Y-%m-%d")
    else:
        target_day = args.day

    stages = {}
    for sym in symbols:
        stages[sym] = compute_snapshot(sym, target_day)

    result = {
        "day": target_day,
        "stages": stages,
        "symbol_count": len(symbols),
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
