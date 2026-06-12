"""
市场状态判断模块
================
基于大盘数据 + 用户主动确认, 判断当前市场处于:
  震荡市 / 上升趋势 / 下跌趋势

输入数据:
  - data/market/daily/amount/daily.jsonl (成交额序列)
  - data/warmup/warmup-60.json (指数60日序列)
  - data/market/breadth-cache.json (涨跌家数)

判断规则:
  上升趋势: 指数在MA20上方 + MA20斜率>0 + 近5日涨>跌天数≥4
  下跌趋势: 指数在MA20下方 + MA20斜率<0 + 近5日跌>涨天数≥4
  震荡市:  其他情况 (指数在MA20附近横盘, 或涨跌交替)

用户可勾选覆盖, 大盘数据做交叉验证提示。
"""
import json
import os
import sys
from datetime import date, timedelta
from typing import Optional, Dict, Any, Tuple

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, ROOT)

STATE_FILE = os.path.join(DIR, "data", "market_state.json")


def _read_json(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _read_jsonl(path: str) -> list:
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return rows


def _read_index_series(warmup_path: str, keys: list) -> list:
    """从 warmup-60.json 读取指定指数序列, 返回 [{date, close, pct}, ...]"""
    w = _read_json(warmup_path)
    if not w:
        return []
    history = w.get("history", {})
    for k in keys:
        if k in history:
            series = history[k]
            if series and len(series) > 0:
                return [{"date": s.get("date", ""), "close": s.get("close", 0),
                         "pct": s.get("pct", 0)} for s in series]
    return []


def _read_breadth(breadth_path: str) -> list:
    """读取涨跌家数序列, 返回 [{date, up, down, flat}, ...]"""
    lines = _read_jsonl(breadth_path)
    result = []
    for l in lines:
        d = l.get("date", l.get("day", ""))
        up = l.get("up") or l.get("advancing", 0)
        down = l.get("down") or l.get("declining", 0)
        if d and (up > 0 or down > 0):
            result.append({"date": d, "up": up, "down": down})
    return result


def _read_volume_series(daily_amount_path: str) -> list:
    """读取成交额序列, 返回 [{date, amount}, ...]"""
    rows = _read_jsonl(daily_amount_path)
    result = []
    for r in rows:
        d = r.get("date", r.get("day", ""))
        amt = r.get("amount", r.get("market_amount", 0))
        if d and amt > 0:
            result.append({"date": d, "amount": amt})
    return result


def _calc_ma(data: list, key: str, period: int) -> list:
    """计算移动平均, 返回与原序列等长的列表"""
    result = [None] * len(data)
    for i in range(len(data)):
        if i < period - 1:
            continue
        window = [d[key] for d in data[i - period + 1:i + 1] if d[key] is not None]
        if window:
            result[i] = sum(window) / len(window)
    return result


def _calc_slope(ma20: list, idx: int, lookback: int = 5) -> Optional[float]:
    """计算MA20在idx处的斜率 (最近lookback个有效值的线性回归斜率)"""
    valid = []
    for i in range(max(0, idx - lookback + 1), idx + 1):
        if i < len(ma20) and ma20[i] is not None:
            valid.append(ma20[i])
    if len(valid) < 2:
        return None
    n = len(valid)
    x_mean = (n - 1) / 2
    y_mean = sum(valid) / n
    num = sum((i - x_mean) * (valid[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0
    return num / den


def detect_market_state(
    warmup_path: str = None,
    breadth_path: str = None,
    daily_amount_path: str = None
) -> dict:
    """
    检测当前市场状态。

    返回:
      {
        "state": "震荡" | "上升" | "下跌",
        "confidence": 0.0 ~ 1.0,
        "indicators": {
          "index_trend": "above_ma" | "below_ma" | "near_ma",
          "ma20_slope": float,
          "breadth_up_days": int,        # 近5日涨>跌的天数
          "breadth_down_days": int,
          "volume_trend": "rising" | "falling" | "flat",
          "index_pct_5d": float,         # 指数近5日涨跌幅
          "index_pct_20d": float
        },
        "as_of": "2026-06-09",
        "user_override": false
      }
    """
    if warmup_path is None:
        warmup_path = os.path.join(ROOT, "data", "warmup", "warmup-60.json")
    if breadth_path is None:
        breadth_path = os.path.join(ROOT, "data", "market", "breadth-cache.json")
    if daily_amount_path is None:
        daily_amount_path = os.path.join(ROOT, "data", "market", "daily", "amount", "daily.jsonl")

    index_series = _read_index_series(warmup_path, ["sh000001", "sh000300"])
    breadth_series = _read_breadth(breadth_path)
    volume_series = _read_volume_series(daily_amount_path)

    indicators = {
        "index_trend": "near_ma",
        "ma20_slope": 0.0,
        "breadth_up_days": 0,
        "breadth_down_days": 0,
        "volume_trend": "flat",
        "index_pct_5d": 0.0,
        "index_pct_20d": 0.0
    }

    if not index_series or len(index_series) < 25:
        return {
            "state": "震荡",
            "confidence": 0.5,
            "indicators": indicators,
            "as_of": str(date.today()),
            "user_override": False
        }

    closes = [s["close"] for s in index_series]
    ma20 = _calc_ma(index_series, "close", 20)
    latest_idx = len(closes) - 1

    latest_close = closes[latest_idx]
    latest_ma20 = ma20[latest_idx]

    if latest_ma20 and latest_ma20 > 0:
        pct_from_ma20 = (latest_close - latest_ma20) / latest_ma20 * 100
    else:
        pct_from_ma20 = 0

    slope = _calc_slope(ma20, latest_idx)
    slope_val = slope if slope is not None else 0.0
    indicators["ma20_slope"] = round(slope_val, 4)

    if pct_from_ma20 > 1.5 and slope_val > 0:
        indicators["index_trend"] = "above_ma"
    elif pct_from_ma20 < -1.5 and slope_val < 0:
        indicators["index_trend"] = "below_ma"
    else:
        indicators["index_trend"] = "near_ma"

    idx_pct_5d = 0
    if len(closes) >= 6:
        idx_pct_5d = (closes[latest_idx] - closes[latest_idx - 5]) / closes[latest_idx - 5] * 100
    indicators["index_pct_5d"] = round(idx_pct_5d, 2)

    idx_pct_20d = 0
    if len(closes) >= 21:
        idx_pct_20d = (closes[latest_idx] - closes[latest_idx - 20]) / closes[latest_idx - 20] * 100
    indicators["index_pct_20d"] = round(idx_pct_20d, 2)

    up_days = 0
    down_days = 0
    if breadth_series:
        recent = breadth_series[-10:]
        for b in recent:
            if b["up"] > b["down"]:
                up_days += 1
            elif b["down"] > b["up"]:
                down_days += 1
    indicators["breadth_up_days"] = up_days
    indicators["breadth_down_days"] = down_days

    vol_slope = _calc_slope_volume(volume_series, 5)
    if vol_slope > 0.05:
        indicators["volume_trend"] = "rising"
    elif vol_slope < -0.05:
        indicators["volume_trend"] = "falling"
    else:
        indicators["volume_trend"] = "flat"

    state, confidence = _classify_state(indicators)

    return {
        "state": state,
        "confidence": confidence,
        "indicators": indicators,
        "as_of": str(date.today()),
        "user_override": False
    }


def _calc_slope_volume(volume_series: list, lookback: int = 5) -> float:
    """计算成交额近N日趋势斜率 (归一化)"""
    if not volume_series or len(volume_series) < lookback:
        return 0.0
    recent = volume_series[-lookback:]
    amounts = [r["amount"] for r in recent if r["amount"] > 0]
    if len(amounts) < 2:
        return 0.0
    avg = sum(amounts) / len(amounts)
    if avg == 0:
        return 0.0
    first_half = amounts[:len(amounts) // 2]
    second_half = amounts[len(amounts) // 2:]
    return (sum(second_half) / len(second_half) - sum(first_half) / len(first_half)) / avg


def _classify_state(indicators: dict) -> Tuple[str, float]:
    trend = indicators["index_trend"]
    up_days = indicators["breadth_up_days"]
    down_days = indicators["breadth_down_days"]
    pct_5d = indicators["index_pct_5d"]
    pct_20d = indicators["index_pct_20d"]
    vol_trend = indicators["volume_trend"]
    slope = indicators["ma20_slope"]

    up_signals = 0
    down_signals = 0

    if trend == "above_ma":
        up_signals += 1
    elif trend == "below_ma":
        down_signals += 1

    if up_days >= 7:
        up_signals += 1
    elif down_days >= 7:
        down_signals += 1

    if pct_5d > 1.0:
        up_signals += 1
    elif pct_5d < -1.0:
        down_signals += 1

    if pct_20d > 3.0:
        up_signals += 1
    elif pct_20d < -3.0:
        down_signals += 1

    if vol_trend == "rising":
        up_signals += 1
    elif vol_trend == "falling":
        down_signals += 1

    if slope > 0.05:
        up_signals += 0.5
    elif slope < -0.05:
        down_signals += 0.5

    total = 5.5
    conf = max(up_signals, down_signals) / total

    if up_signals >= 3:
        return "上升", min(conf, 0.95)
    elif down_signals >= 3:
        return "下跌", min(conf, 0.95)
    else:
        return "震荡", 0.5 + (abs(up_signals - down_signals) / total)


def load_market_state() -> dict:
    """加载持久化的市场状态 (含用户覆盖)"""
    saved = _read_json(STATE_FILE)
    if saved:
        return saved
    return {
        "state": "震荡",
        "confidence": 0.5,
        "indicators": {},
        "as_of": str(date.today()),
        "user_override": False,
        "user_state": None,
        "history": []
    }


def save_market_state(state: dict):
    """持久化市场状态"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

    history = state.get("history", [])
    entry = {
        "date": state.get("as_of", str(date.today())),
        "detected_state": state.get("state", ""),
        "confidence": state.get("confidence", 0),
        "user_override": state.get("user_override", False),
        "user_state": state.get("user_state"),
        "indicators": state.get("indicators", {})
    }
    if not history or history[-1].get("date") != entry["date"]:
        history.append(entry)
    if len(history) > 60:
        history = history[-60:]
    state["history"] = history

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def apply_user_override(target_state: str) -> dict:
    """用户手动设置市场状态"""
    valid = ["震荡", "上升", "下跌"]
    if target_state not in valid:
        raise ValueError(f"无效状态: {target_state}, 可选: {valid}")

    current = load_market_state()

    auto = detect_market_state()
    current["indicators"] = auto.get("indicators", {})
    current["as_of"] = str(date.today())
    current["user_override"] = True
    current["user_state"] = target_state
    current["state"] = target_state
    current["confidence"] = 1.0

    save_market_state(current)
    return current


def clear_user_override() -> dict:
    """清除用户覆盖, 恢复自动判断"""
    auto = detect_market_state()
    state = {
        "state": auto["state"],
        "confidence": auto["confidence"],
        "indicators": auto["indicators"],
        "as_of": str(date.today()),
        "user_override": False,
        "user_state": None,
        "history": []
    }
    save_market_state(state)
    return state


def get_effective_state() -> dict:
    """
    获取当前有效的市场状态。
    优先使用持久化状态 (含用户覆盖),
    若无则自动检测并保存。
    """
    saved = load_market_state()
    today_str = str(date.today())

    if saved.get("as_of") == today_str:
        return saved

    auto = detect_market_state()
    if saved.get("user_override"):
        saved["indicators"] = auto["indicators"]
        saved["as_of"] = today_str
        save_market_state(saved)
        return saved

    state = {
        "state": auto["state"],
        "confidence": auto["confidence"],
        "indicators": auto["indicators"],
        "as_of": today_str,
        "user_override": False,
        "user_state": None,
        "history": []
    }
    save_market_state(state)
    return state


def get_tech_etf_symbols() -> list:
    """返回科技板块 ETF symbol 列表"""
    return ["sh512480", "sh515880", "sh516510", "sh516010", "sh563530", "sh562500", "sh515120"]


def get_resource_etf_symbols() -> list:
    """返回资源板块 ETF symbol 列表"""
    return ["sh512400", "sh516160"]


if __name__ == "__main__":
    result = detect_market_state()
    print(json.dumps(result, ensure_ascii=False, indent=2))
