"""
震荡市投资策略模块
==================
适配震荡行情 (2026年6月场景) 的建仓/套利/行情切换规则。

核心规则:
  1. 分批次建6成底仓 (3批, 每批 20%目标仓位)
  2. 单只科技股上涨5% → 减持总仓位的10%做短线套利
  3. 单只科技股下跌3% → 加仓总仓位的10%低位吸筹
  4. 上升趋势确认后 → 波段仓位转回底仓, 持有等待上涨

状态持久化: 波段策略/data/ranged_state.json
"""
import json
import os
import sys
from datetime import date, timedelta
from typing import Optional, Dict, Any, List, Tuple

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(DIR)
sys.path.insert(0, ROOT)

STATE_FILE = os.path.join(DIR, "data", "ranged_state.json")

TECH_ETF_SYMBOLS = [
    "sh512480",  # 半导体
    "sh515880",  # 通信
    "sh516510",  # 云计算
    "sh516010",  # 游戏
    "sh563530",  # 商业航天
    "sh562500",  # 机器人
    "sh515120",  # 创新药
]

SYMBOL_NAMES = {
    "sh512480": "半导体ETF",
    "sh515880": "通信ETF",
    "sh516510": "云计算ETF",
    "sh516010": "游戏ETF",
    "sh563530": "商业航天ETF",
    "sh562500": "机器人ETF",
    "sh515120": "创新药ETF",
}

DEFAULT_CONFIG = {
    "base_ratio": 0.6,          # 底仓占总资金比例
    "batches": 3,               # 建仓批次
    "batch_ratio": 0.2,         # 每批次占总资金比例 (3×20%=60%)
    "sell_trigger_pct": 5.0,    # 涨幅触发套利阈值
    "sell_ratio": 0.10,         # 每次卖出总仓位的比例
    "buy_trigger_pct": 3.0,     # 跌幅触发加仓阈值
    "buy_ratio": 0.10,          # 每次买入总仓位的比例
    "cooldown_days": 1,         # 同向操作冷却天数 (防止同一天触发多次)
    "uptrend_merge": True       # 上升趋势确认后合并波段仓
}


def _read_json(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _read_warmup_prices(warmup_path: str = None) -> dict:
    """从 warmup-60.json 读取最新价格"""
    if warmup_path is None:
        warmup_path = os.path.join(ROOT, "data", "warmup", "warmup-60.json")
    w = _read_json(warmup_path)
    if not w:
        return {}
    history = w.get("history", {})
    prices = {}
    for sym in TECH_ETF_SYMBOLS:
        series = history.get(sym, [])
        if series and len(series) > 0:
            last = series[-1]
            prices[sym] = {
                "price": last.get("close", 0),
                "date": last.get("date", ""),
                "pct": last.get("pct", 0)
            }
    return prices


def get_default_state() -> dict:
    return {
        "positions": {},
        "total_capital": 100000,
        "config": dict(DEFAULT_CONFIG),
        "current_phase": "idle",       # idle | building | holding | uptrend
        "base_built_pct": 0.0,         # 底仓已建比例
        "last_update": str(date.today()),
        "history": []
    }


def load_ranged_state() -> dict:
    saved = _read_json(STATE_FILE)
    if saved:
        for k in ("positions", "config", "history"):
            if k not in saved:
                saved[k] = get_default_state()[k]
        if "total_capital" not in saved:
            saved["total_capital"] = 100000
        if "current_phase" not in saved:
            saved["current_phase"] = "idle"
        if "base_built_pct" not in saved:
            saved["base_built_pct"] = 0.0
        config = saved.get("config", {})
        for k, v in DEFAULT_CONFIG.items():
            if k not in config:
                config[k] = v
        saved["config"] = config
        return saved
    return get_default_state()


def save_ranged_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["last_update"] = str(date.today())
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _init_position(sym: str, target_pct: float) -> dict:
    return {
        "symbol": sym,
        "name": SYMBOL_NAMES.get(sym, sym),
        "target_pct": target_pct,
        "base_shares": 0,
        "base_avg_cost": 0.0,
        "base_target_shares": 0,
        "swing_lots": [],
        "building_phase": 0,
        "last_price": 0.0,
        "last_price_date": "",
        "last_signal": None,
        "last_signal_date": None,
        "status": "idle"
    }


def compute_signals(
    total_capital: float = None,
    warmup_path: str = None,
    force_refresh: bool = False
) -> dict:
    """
    计算震荡市策略信号。

    返回:
      {
        "current_phase": "idle" | "building" | "holding" | "uptrend",
        "base_built_pct": 0.0 ~ 1.0 (建仓进度),
        "positions": { sym: { ..., signal, action_amount, ... } },
        "signals": [ { symbol, name, signal_type, action, amount, reason } ],
        "summary": "..."
      }
    """
    state = load_ranged_state()
    config = state.get("config", DEFAULT_CONFIG)
    total_capital = total_capital or state.get("total_capital", 100000)
    prices = _read_warmup_prices(warmup_path)

    today = str(date.today())

    from .market_state import get_effective_state
    try:
        ms = get_effective_state()
        market_state = ms.get("state", "震荡")
    except Exception:
        market_state = "震荡"

    n = len(TECH_ETF_SYMBOLS)
    per_symbol_target = (config["base_ratio"] * total_capital) / n

    positions = state.get("positions", {})
    for sym in TECH_ETF_SYMBOLS:
        if sym not in positions:
            positions[sym] = _init_position(sym, config["base_ratio"] / n)

    base_built_total = 0.0
    for sym in TECH_ETF_SYMBOLS:
        pos = positions[sym]
        if prices.get(sym):
            pos["last_price"] = prices[sym]["price"]
            pos["last_price_date"] = prices[sym]["date"]
        if pos["base_target_shares"] > 0:
            base_built_total += min(1.0, pos["base_shares"] / pos["base_target_shares"])

    base_built_pct = base_built_total / n if n > 0 else 0.0

    phase = "idle"
    if market_state == "上升":
        phase = "uptrend"
    elif base_built_pct < config["base_ratio"]:
        phase = "building"
    elif base_built_pct >= config["base_ratio"]:
        phase = "holding"

    signals = []
    today_signals = []

    for sym in TECH_ETF_SYMBOLS:
        pos = positions[sym]
        price = pos.get("last_price", 0)
        if not price or price <= 0:
            continue

        total_cost = pos["base_avg_cost"] or price
        pct_change = (price - total_cost) / total_cost * 100 if total_cost > 0 else 0

        total_shares = pos["base_shares"] + sum(lot.get("shares", 0) for lot in pos.get("swing_lots", []))
        total_value = total_shares * price
        position_ratio = total_value / total_capital if total_capital > 0 else 0

        signal = None

        if phase == "building" and pos["base_shares"] < pos.get("base_target_shares", 0):
            batch_target = per_symbol_target / config["batches"]
            current_batches = pos.get("building_phase", 0)
            target_batches = config["batches"]

            if current_batches < target_batches:
                batch_amount = batch_target
                batch_shares = int(batch_amount / price / 100) * 100
                if batch_shares >= 100:
                    signal = {
                        "symbol": sym,
                        "name": SYMBOL_NAMES.get(sym, sym),
                        "signal_type": "build_batch",
                        "action": "buy",
                        "reason": f"第{current_batches + 1}批建底仓 ({current_batches + 1}/{target_batches})",
                        "amount": batch_amount,
                        "shares": batch_shares,
                        "price": price
                    }
                    today_signals.append(signal)

        elif phase == "holding":
            last_sig = pos.get("last_signal")
            last_sig_date = pos.get("last_signal_date", "")

            if last_sig_date == today and not force_refresh:
                continue

            if pct_change >= config["sell_trigger_pct"] and total_shares > 0 and last_sig != "sell":
                sell_value = total_value * config["sell_ratio"]
                sell_shares = int(sell_value / price / 100) * 100
                if sell_shares >= 100:
                    signal = {
                        "symbol": sym,
                        "name": SYMBOL_NAMES.get(sym, sym),
                        "signal_type": "take_profit",
                        "action": "sell",
                        "reason": f"涨幅{pct_change:.1f}%触发套利, 减持10%",
                        "amount": sell_value,
                        "shares": sell_shares,
                        "price": price
                    }
                    pos["last_signal"] = "sell"
                    pos["last_signal_date"] = today
                    today_signals.append(signal)

            elif pct_change <= -config["buy_trigger_pct"] and position_ratio < config["base_ratio"] and last_sig != "buy":
                buy_value = total_capital * config["buy_ratio"]
                buy_shares = int(buy_value / price / 100) * 100
                if buy_shares >= 100:
                    signal = {
                        "symbol": sym,
                        "name": SYMBOL_NAMES.get(sym, sym),
                        "signal_type": "dip_buy",
                        "action": "buy",
                        "reason": f"跌幅{pct_change:.1f}%触发吸筹, 加仓10%",
                        "amount": buy_value,
                        "shares": buy_shares,
                        "price": price
                    }
                    pos["last_signal"] = "buy"
                    pos["last_signal_date"] = today
                    today_signals.append(signal)

        elif phase == "uptrend":
            if pos.get("swing_lots") and config.get("uptrend_merge", True):
                swing_total = sum(lot.get("shares", 0) for lot in pos["swing_lots"])
                if swing_total > 0:
                    signal = {
                        "symbol": sym,
                        "name": SYMBOL_NAMES.get(sym, sym),
                        "signal_type": "merge_to_base",
                        "action": "hold",
                        "reason": "上升趋势确认, 波段仓转底仓持有",
                        "amount": 0,
                        "shares": swing_total,
                        "price": price
                    }
                    today_signals.append(signal)

        if signal:
            signals.append(signal)

    state["current_phase"] = phase
    state["base_built_pct"] = base_built_pct
    state["total_capital"] = total_capital
    state["positions"] = positions

    state.setdefault("history", [])
    if today_signals:
        state["history"].append({
            "date": today,
            "phase": phase,
            "signals": [{"symbol": s["symbol"], "type": s["signal_type"], "action": s["action"]}
                        for s in today_signals]
        })
        if len(state["history"]) > 200:
            state["history"] = state["history"][-200:]

    save_ranged_state(state)

    summary_parts = []
    if phase == "building":
        summary_parts.append(f"震荡市底仓建设中 ({base_built_pct*100:.0f}%), 目标60%")
    elif phase == "holding":
        summary_parts.append(f"震荡市底仓完成, 等待套利/吸筹信号")
    elif phase == "uptrend":
        summary_parts.append(f"上升趋势已确认, 底仓持有等待上涨")
    else:
        summary_parts.append("等待建仓时机")

    hold_count = 0
    buy_count = 0
    sell_count = 0
    for s in today_signals:
        if s["signal_type"] == "build_batch":
            buy_count += 1
        elif s["signal_type"] == "take_profit":
            sell_count += 1
        elif s["signal_type"] == "dip_buy":
            buy_count += 1
        elif s["signal_type"] == "merge_to_base":
            hold_count += 1

    if buy_count:
        summary_parts.append(f"买入信号: {buy_count}只")
    if sell_count:
        summary_parts.append(f"卖出信号: {sell_count}只")
    if hold_count:
        summary_parts.append(f"波段合并: {hold_count}只")

    return {
        "current_phase": phase,
        "market_state": market_state,
        "base_built_pct": round(base_built_pct, 4),
        "positions": {sym: {
            "symbol": p["symbol"],
            "name": p["name"],
            "base_shares": p["base_shares"],
            "base_avg_cost": round(p["base_avg_cost"], 4),
            "swing_shares": sum(lot.get("shares", 0) for lot in p.get("swing_lots", [])),
            "last_price": p.get("last_price", 0),
            "total_value": round(
                (p["base_shares"] + sum(lot.get("shares", 0) for lot in p.get("swing_lots", [])))
                * max(p.get("last_price", 0), 0), 2
            ),
            "status": p.get("status", "idle"),
            "building_phase": p.get("building_phase", 0)
        } for sym, p in positions.items()},
        "signals": signals,
        "summary": " | ".join(summary_parts),
        "config": config,
        "total_capital": total_capital,
        "as_of": today
    }


def execute_signal(sym: str, signal_type: str) -> dict:
    """
    执行单笔策略信号, 更新 position 状态。

    支持的操作:
      - build_batch: 完成一批底仓建仓
      - take_profit: 记录套利卖出 (swing_lot 出)
      - dip_buy: 记录吸筹加仓 (swing_lot 入)
      - merge_to_base: 波段仓合并到底仓
    """
    state = load_ranged_state()
    positions = state.get("positions", {})
    config = state.get("config", DEFAULT_CONFIG)

    if sym not in positions:
        return {"ok": False, "error": f"未找到 {sym}"}

    pos = positions[sym]
    price = pos.get("last_price", 0)

    if signal_type == "build_batch":
        batch_target = state["total_capital"] * pos["target_pct"] / config["batches"]
        batch_shares = int(batch_target / price / 100) * 100 if price > 0 else 0
        if batch_shares > 0:
            new_cost = (
                (pos["base_shares"] * pos["base_avg_cost"] + batch_shares * price)
                / (pos["base_shares"] + batch_shares)
            ) if (pos["base_shares"] + batch_shares) > 0 else price
            pos["base_shares"] += batch_shares
            pos["base_avg_cost"] = new_cost
            pos["building_phase"] += 1
            pos["status"] = "building"
            if pos["building_phase"] >= config["batches"]:
                pos["status"] = "holding"

    elif signal_type == "take_profit":
        total_shares = pos["base_shares"] + sum(lot.get("shares", 0) for lot in pos.get("swing_lots", []))
        sell_shares = int(total_shares * config["sell_ratio"] / 100) * 100
        if sell_shares < 100:
            sell_shares = 100

        remaining = sell_shares
        if pos["swing_lots"]:
            new_lots = []
            for lot in pos["swing_lots"]:
                l_shares = lot.get("shares", 0)
                if remaining > 0 and l_shares > 0:
                    taken = min(remaining, l_shares)
                    remaining -= taken
                    if l_shares > taken:
                        new_lots.append({"shares": l_shares - taken, "cost": lot["cost"],
                                         "entry_date": lot.get("entry_date", "")})
                else:
                    new_lots.append(lot)
            pos["swing_lots"] = new_lots

        if remaining > 0 and pos["base_shares"] > 0:
            pos["base_shares"] = max(0, pos["base_shares"] - remaining)

        pos["last_signal"] = "sell"

    elif signal_type == "dip_buy":
        buy_value = state["total_capital"] * config["buy_ratio"]
        buy_shares = int(buy_value / price / 100) * 100 if price > 0 else 0
        if buy_shares >= 100:
            pos["swing_lots"].append({
                "shares": buy_shares,
                "cost": price,
                "entry_date": str(date.today())
            })
        pos["last_signal"] = "buy"

    elif signal_type == "merge_to_base":
        swing_total = sum(lot.get("shares", 0) for lot in pos.get("swing_lots", []))
        if swing_total > 0:
            swing_cost_total = sum(lot.get("shares", 0) * lot.get("cost", 0)
                                   for lot in pos["swing_lots"])
            total_shares = pos["base_shares"] + swing_total
            pos["base_avg_cost"] = (
                (pos["base_shares"] * pos["base_avg_cost"] + swing_cost_total) / total_shares
            ) if total_shares > 0 else 0
            pos["base_shares"] = total_shares
            pos["swing_lots"] = []
        pos["status"] = "uptrend"

    pos["last_signal_date"] = str(date.today())
    state["positions"] = positions
    save_ranged_state(state)

    return {"ok": True, "position": {
        "symbol": pos["symbol"],
        "base_shares": pos["base_shares"],
        "base_avg_cost": round(pos["base_avg_cost"], 4),
        "swing_shares": sum(lot["shares"] for lot in pos.get("swing_lots", [])),
        "status": pos["status"]
    }}


def reset_ranged_state(total_capital: float = 100000) -> dict:
    """重置震荡市策略状态 (清空所有仓位)"""
    state = get_default_state()
    state["total_capital"] = total_capital
    for sym in TECH_ETF_SYMBOLS:
        state["positions"][sym] = _init_position(sym, DEFAULT_CONFIG["base_ratio"] / len(TECH_ETF_SYMBOLS))
    save_ranged_state(state)
    return state


def update_config(new_config: dict) -> dict:
    state = load_ranged_state()
    config = state.get("config", DEFAULT_CONFIG)
    for k, v in new_config.items():
        if k in DEFAULT_CONFIG:
            config[k] = float(v) if isinstance(DEFAULT_CONFIG[k], float) else v
    state["config"] = config
    save_ranged_state(state)
    return state


if __name__ == "__main__":
    result = compute_signals()
    print(json.dumps(result, ensure_ascii=False, indent=2))
