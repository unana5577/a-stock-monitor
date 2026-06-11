"""
阶段检测器 — 每ETF独立判断四个阶段
====================================
输入: 日线序列 (date, open, high, low, close, pct, amount, vol)
输出: 震荡 / 启动 / 主升 / 防守

5条规则按优先级 S1→S5:
  S1(防守): close < MA60 且 MA20 < MA60         → 空头排列
  S2(主升): close > MA20 > MA60 且 MA20斜率>0    → 强势多头
  S3(启动): close > MA20 且 MA20斜率刚转正 且 量放大 → 趋势萌芽
  S4(震荡): close 在 MA20±3% 或 MA20斜率≈0       → 横盘
  默认: 震荡
"""
import math
from typing import List, Dict, Tuple, Optional

STAGE_RANGED    = "震荡"
STAGE_STARTUP   = "启动"
STAGE_UPTREND   = "主升"
STAGE_DECLINING = "下跌"
STAGE_DEFENSE   = "防守"


def calc_ma(data: List[float], period: int) -> List[Optional[float]]:
    result = [None] * len(data)
    for i in range(len(data)):
        if i < period - 1:
            continue
        window = data[i - period + 1:i + 1]
        if window:
            result[i] = sum(window) / len(window)
    return result


def calc_slope(series: List[Optional[float]], idx: int, lookback: int = 5) -> Optional[float]:
    """最近lookback个有效值的线性回归斜率"""
    valid = []
    for i in range(max(0, idx - lookback + 1), idx + 1):
        if i < len(series) and series[i] is not None:
            valid.append(series[i])
    if len(valid) < 2:
        return None
    n = len(valid)
    x_mean = (n - 1) / 2
    y_mean = sum(valid) / n
    num = sum((i - x_mean) * (valid[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return (num / den) if den != 0 else 0.0


def recent_min(data: List[float], start_idx: int, window: int) -> Optional[float]:
    """start_idx往前window个值的最小值"""
    vals = data[max(0, start_idx - window + 1):start_idx + 1]
    return min(vals) if vals else None


def detect_stage(rows: List[dict], idx: int) -> Tuple[str, dict]:
    """
    对单只ETF在idx位置的日线, 返回 (阶段名, 诊断信息)。

    rows: 完整的日线序列 [{date, close, amount, ...}]
    idx:  当前要判断的位置 (0-based)
    """
    closes = [r["close"] for r in rows]
    amounts = [r.get("amount", 0) for r in rows]
    vols = [r.get("vol", 0) for r in rows]

    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)

    diag = {
        "close": round(closes[idx], 4),
        "ma20": round(ma20[idx], 4) if ma20[idx] else None,
        "ma60": round(ma60[idx], 4) if ma60[idx] else None,
        "ma20_slope": None,
        "vol_ratio": None,
    }

    if idx < 60:
        return STAGE_RANGED, diag

    c = closes[idx]
    m20 = ma20[idx]
    m60 = ma60[idx]
    if m20 is None or m60 is None or m20 <= 0 or m60 <= 0:
        return STAGE_RANGED, diag

    m20_slope = calc_slope(ma20, idx, 5)
    diag["ma20_slope"] = round(m20_slope, 6) if m20_slope is not None else None

    # volume ratio: 近3日均量 / 20日均量
    vol_window = [v for v in vols[idx-2:idx+1] if v > 0]
    vol_avg20 = sum(vol for vol in vols[idx-19:idx+1] if vol > 0) / max(1, sum(1 for v in vols[idx-19:idx+1] if v > 0))
    vol_avg3 = sum(vol_window) / len(vol_window) if vol_window else 0
    diag["vol_ratio"] = round(vol_avg3 / vol_avg20, 2) if vol_avg20 > 0 else None

    # ma20_slope_prev: 前5日的斜率 (用于判断"刚拐头")
    m20_slope_prev = calc_slope(ma20, idx - 5, 5)
    slope_turning = (
        m20_slope is not None and m20_slope > 0 and
        (m20_slope_prev is None or m20_slope_prev <= 0.0)
    )

    # 5日最低价 vs 10日最低价 (不创新低)
    low5 = recent_min(closes, idx, 5)
    low10 = recent_min(closes, idx, 10)
    no_new_low = (low5 is not None and low10 is not None and low5 > low10)

    pct_from_ma20 = (c - m20) / m20 * 100

    # S1: 防守 — 均线空头排列 (close < MA60 且 MA20 < MA60)
    if c < m60 and m20 < m60:
        return STAGE_DEFENSE, diag

    # S2: 主升 — 多头排列, 趋势确立 (MA20>MA60 + 斜率>0 + 不创新低)
    # 用持久化防抖动(backtest层处理)，此处只做单日判断
    if c > m20 > m60 and m20_slope is not None and m20_slope > 0:
        if no_new_low:
            return STAGE_UPTREND, diag
        return STAGE_STARTUP, diag

    # S3: 启动 — 价格突破MA20但MA20仍在MA60下方 (或刚突破), 斜率转正
    if c > m20 and m20_slope is not None and m20_slope > 0:
        return STAGE_STARTUP, diag

    # S4: 下跌 — 趋势转弱预警 (close<MA20 且 斜率<0 但 MA20>MA60, 还没死叉)
    if c < m20 and m20_slope is not None and m20_slope < 0 and m20 > m60:
        return STAGE_DECLINING, diag

    # S5: 震荡 — MA20附近横盘 或 斜率近零
    if abs(pct_from_ma20) <= 3.0:
        return STAGE_RANGED, diag
    if m20_slope is not None and abs(m20_slope) < 0.3:
        return STAGE_RANGED, diag

    # default
    return STAGE_RANGED, diag


def detect_all_stages(rows: List[dict]) -> List[dict]:
    """对完整序列逐日判断阶段, 返回 [{date, stage, ...}]"""
    results = []
    for i in range(len(rows)):
        stage, diag = detect_stage(rows, i)
        results.append({
            "date": rows[i]["date"],
            "close": rows[i]["close"],
            "stage": stage,
            **diag
        })
    return results
