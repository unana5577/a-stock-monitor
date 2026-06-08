"""
波段策略 — Policy 层状态机
============================
基于现有 lifecycle 信号输出,维护每只 ETF 的波段持仓状态机。

状态：OUT → BUILDING ⇄ IN → COOLING → OUT

依赖（不改动）：
  treasolo/m1_sector_lifecycle.py → 动能/资金行为/阶段信号/指标数据

本模块独立于 lifecycle,不修改任何原有代码。
"""
import json
import math
import os
from typing import Optional, Dict, Any, Tuple
from copy import deepcopy

DIR = os.path.dirname(os.path.abspath(__file__))
STATES_DIR = os.path.join(DIR, "data", "states")
PARAMS_PATH = os.path.join(DIR, "params.json")


def load_params() -> dict:
    if os.path.exists(PARAMS_PATH):
        with open(PARAMS_PATH) as f:
            return json.load(f)
    return {}


def get_default_state(symbol: str, pct_p80: float = 1.5) -> dict:
    params = load_params()
    warn, exec_line = calc_stop_lines(pct_p80, params)
    return {
        "symbol": symbol,
        "trend_state": "OUT",
        "exit_reason": None,
        "exit_date": None,
        "entry_date": None,
        "position_level": 0.0,
        "target_weight": 0.0,
        "peak_equity": 0.0,
        "pct_p80": pct_p80,
        "stop_warn_line": warn,
        "stop_exec_line": exec_line,
        "building_entry_low": None,
        "as_of": None,
        "history": []
    }


def load_state(symbol: str, pct_p80: float = 1.5) -> dict:
    path = os.path.join(STATES_DIR, f"{symbol}.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return get_default_state(symbol, pct_p80)


def save_state(state: dict):
    os.makedirs(STATES_DIR, exist_ok=True)
    path = os.path.join(STATES_DIR, f"{state['symbol']}.json")
    with open(path, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def append_history(state: dict, date: str, entry: dict):
    history = state.get("history", [])
    if history and history[-1].get("date") == date:
        history[-1] = entry
    else:
        history.append(entry)
    if len(history) > 200:
        history = history[-200:]
    state["history"] = history


# ============================================================
# 止损线计算
# ============================================================

def calc_stop_lines(pct_p80: float, params: dict = None) -> Tuple[float, float]:
    if params is None:
        params = load_params()
    warn_mult = params.get("p80_stop_warn_mult", 5)
    exec_mult = params.get("p80_stop_exec_mult", 8)
    warn_cap = params.get("stop_warn_cap", 12.0)
    exec_cap = params.get("stop_exec_cap", 18.0)
    return round(min(pct_p80 * warn_mult, warn_cap), 1), round(min(pct_p80 * exec_mult, exec_cap), 1)


# ============================================================
# 信号强度
# ============================================================

MOMENTUM_RANK = {
    "强势向上": 5, "偏强向上": 4, "中性震荡": 2,
    "弱势反弹": 1, "弱势向下": 0, "偏强向下": 0, "强势向下": 0
}


def is_momentum_healthy(momentum: str) -> bool:
    return momentum in ("强势向上", "偏强向上")


def get_signal_strength(momentum: str) -> str:
    if momentum == "强势向上":
        return "强"
    if momentum == "偏强向上":
        return "中"
    if momentum == "中性震荡":
        return "弱"
    return "—"


def momentum_downgraded(yesterday_momentum: str, today_momentum: str) -> bool:
    return MOMENTUM_RANK.get(today_momentum, 0) < MOMENTUM_RANK.get(yesterday_momentum, 0)


# ============================================================
# Feature 辅助
# ============================================================

def get_bias(ind: dict) -> float:
    b = ind.get("Bias_20", ind.get("Bias_20_Pct", ind.get("bias_20", 0)))
    return float(b) if b is not None else 0.0


def get_bias_max(ind: dict) -> Optional[float]:
    v = ind.get("Bias_20_History_Max", ind.get("Bias_20_History_Max_Pct"))
    return float(v) if v is not None and v != 0 else None


def get_close(ind: dict) -> float:
    return float(ind.get("close", ind.get("Close", 0)) or 0)


def get_ma20_slope(ind: dict) -> float:
    return float(ind.get("MA20_Slope", ind.get("ma20_slope", 0)) or 0)


def get_ma60_slope(ind: dict) -> float:
    return float(ind.get("MA60_Slope", ind.get("ma60_slope", 0)) or 0)


def calc_price_factor(bias20: float, history_max: Optional[float], discount: float = 0.5) -> float:
    if bias20 <= 0 or not history_max or history_max == 0:
        return 1.0
    factor = 1.0 - (bias20 / history_max) * discount
    return max(0.5, min(1.0, factor))


# ============================================================
# 入场判定
# ============================================================

def check_entry_r0(signals: dict, ind: dict) -> bool:
    """筑底试探: 磨底期/潜伏期 + Bias收敛 + 不创新低"""
    stage = signals.get("阶段信号", "")
    bias = get_bias(ind)
    params = load_params()

    if stage not in ("磨底期", "潜伏期"):
        return False

    if bias < params.get("building_bias_min", -5.0) or bias > params.get("building_bias_max", 3.0):
        return False

    bias_max = get_bias_max(ind)
    if bias_max and bias > 0 and bias >= params.get("overheat_ratio", 0.9) * bias_max:
        return False

    return True


def check_entry_r0_new_lows(signals: dict, ind: dict, daily_raw: list = None) -> bool:
    """检查近5日最低价 > 近10日最低价（需日线原始数据）"""
    if not daily_raw or len(daily_raw) < 10:
        return False
    last5 = [d.get("low", d.get("close", 0)) for d in daily_raw[-5:]]
    last10 = [d.get("low", d.get("close", 0)) for d in daily_raw[-10:]]
    low5 = min(last5) if last5 else 0
    low10 = min(last10) if last10 else 0
    return low5 > low10


def check_entry_r1(signals: dict, ind: dict) -> bool:
    """趋势确认入场: 热度连升3天 + Change20>0 + 动能健康 + 不过热"""
    momentum = signals.get("动能", "")
    params = load_params()

    if not is_momentum_healthy(momentum):
        return False

    days_up = ind.get("Amount_Share_DaysUp", 0)
    if days_up < params.get("heat_up_days", 3):
        return False

    change20 = ind.get("Amount_Share_Change20")
    if change20 is not None and change20 <= 0:
        return False

    bias = get_bias(ind)
    bias_max = get_bias_max(ind)
    if bias_max and bias > 0 and bias >= params.get("overheat_ratio", 0.9) * bias_max:
        return False

    return True


# ============================================================
# 补仓判定
# ============================================================

def check_topup(signals: dict, ind: dict, yesterday_state: dict) -> Optional[str]:
    params = load_params()
    momentum = signals.get("动能", "")
    bias = get_bias(ind)
    ma60_slope = get_ma60_slope(ind)

    if not is_momentum_healthy(momentum):
        return None

    yest_momentum = ""
    if yesterday_state.get("history"):
        for h in reversed(yesterday_state["history"]):
            if h.get("momentum"):
                yest_momentum = h["momentum"]
                break

    # R1c: 信号升级
    if yest_momentum == "偏强向上" and momentum == "强势向上":
        return "信号升级补仓"

    # R1a: MA20回调
    if bias <= params.get("topup_bias_ma20", 3.0):
        return f"MA20回调补仓(Bias={bias:.1f}%)"

    # R1b: MA60回调
    if bias <= params.get("topup_bias_ma60", 0.0) and ma60_slope > 0:
        return f"MA60回调补仓(Bias={bias:.1f}%)"

    return None


# ============================================================
# 出场判定
# ============================================================

def check_cut(signals: dict, ind: dict, yesterday_state: dict) -> Optional[dict]:
    """分级减仓: 返回 { action, position_level, reason } 或 None"""
    momentum = signals.get("动能", "")
    behavior = signals.get("资金行为", "")
    params = load_params()
    current_level = yesterday_state.get("position_level", 1.0)

    yest_momentum = ""
    if yesterday_state.get("history"):
        for h in reversed(yesterday_state["history"]):
            if h.get("momentum"):
                yest_momentum = h["momentum"]
                break

    # R2a: 动能减弱 (强势→偏强)
    if yest_momentum == "强势向上" and momentum == "偏强向上":
        return {
            "action": "CUT",
            "position_level": min(current_level, 0.7),
            "reason": "动能减弱: 强势→偏强, 减仓至70%"
        }

    # R2a: 资金撤退
    if behavior == "资金撤退" and current_level > 0.7:
        return {
            "action": "CUT",
            "position_level": 0.7,
            "reason": "资金行为: 资金撤退, 减仓至70%"
        }

    # R2b: 趋势转弱 (偏强→中性)
    if yest_momentum == "偏强向上" and momentum == "中性震荡":
        return {
            "action": "CUT",
            "position_level": min(current_level, 0.4),
            "reason": "趋势转弱: 偏强→中性, 减仓至40%"
        }

    # R2b: 加速赶顶
    if behavior == "加速赶顶":
        return {
            "action": "CUT",
            "position_level": min(current_level, 0.4),
            "reason": "资金行为: 加速赶顶, 减仓至40%"
        }

    # R2b: 预过热
    bias = get_bias(ind)
    bias_max = get_bias_max(ind)
    if bias_max and bias > 0 and bias >= params.get("pre_overheat_ratio", 0.85) * bias_max:
        return {
            "action": "CUT",
            "position_level": min(current_level, 0.4),
            "reason": f"预过热: Bias={bias:.1f}%, 接近极值{bias_max:.1f}%"
        }

    return None


def check_exit(signals: dict, ind: dict) -> Optional[str]:
    """清仓判定: 返回 exit_reason 或 None"""
    momentum = signals.get("动能", "")
    behavior = signals.get("资金行为", "")
    stage = signals.get("阶段信号", "")
    advice = signals.get("操作建议", "")
    combo_name = signals.get("显示名称", "")
    params = load_params()

    # R2c: 动能趋势破坏
    if momentum in ("弱势向下", "偏强向下"):
        return "trend_break"

    # R2c: 过热
    bias = get_bias(ind)
    bias_max = get_bias_max(ind)
    if bias_max and bias > 0 and bias >= params.get("overheat_ratio", 0.9) * bias_max:
        return "overheat"

    # R2c: 阶段转坏
    if stage == "衰退期":
        return "stage_bad"
    if advice in ("果断清仓", "清仓离场"):
        return "stage_bad"

    # R2d: 恐慌
    if behavior == "恐慌出逃":
        return "panic"

    return None


# ============================================================
# 止损判定
# ============================================================

def check_stop_loss(signals: dict, ind: dict, state_yesterday: dict) -> Optional[dict]:
    current_level = state_yesterday.get("position_level", 0)
    if current_level <= 0:
        return None

    warn_line = state_yesterday.get("stop_warn_line", 8.0)
    exec_line = state_yesterday.get("stop_exec_line", 12.0)
    peak = state_yesterday.get("peak_equity", 0)
    close = get_close(ind)

    if not peak or peak <= 0:
        return None

    drawdown = (peak - close) / peak * 100

    if drawdown >= exec_line:
        return {
            "action": "STOP_EXIT",
            "position_level": 0.0,
            "reason": f"止损清仓: 回撤{drawdown:.1f}% ≥ 执行线{exec_line}%"
        }

    if drawdown >= warn_line and current_level > 0.5:
        return {
            "action": "STOP_WARN",
            "position_level": current_level * 0.5,
            "reason": f"止损减仓: 回撤{drawdown:.1f}% ≥ 预警线{warn_line}%"
        }

    return None


# ============================================================
# 冷却判定
# ============================================================

def check_cooldown_release(signals: dict, ind: dict, state_yesterday: dict) -> Optional[dict]:
    exit_reason = state_yesterday.get("exit_reason", "")
    params = load_params()

    if exit_reason == "overheat":
        bias = get_bias(ind)
        bias_max = get_bias_max(ind)
        if bias <= 0:
            return {"trend_state": "OUT", "action": "NONE",
                    "reason": "过热冷却解除(Bias转负)", "cooldown_left": 0}
        if bias_max and bias <= params.get("bias_reset_ratio", 0.6) * bias_max:
            return {"trend_state": "OUT", "action": "NONE",
                    "reason": f"过热冷却解除(Bias={bias:.1f}% ≤ {params['bias_reset_ratio']}×Max)",
                    "cooldown_left": 0}
    else:
        momentum = signals.get("动能", "")
        days_up = ind.get("Amount_Share_DaysUp", 0)
        if is_momentum_healthy(momentum) and days_up >= 1:
            return {"trend_state": "OUT", "action": "NONE",
                    "reason": "趋势恢复, 冷却解除", "cooldown_left": 0}

    return None


def check_building_fail(signals: dict, ind: dict, state_yesterday: dict) -> bool:
    """筑底失败: 5日内创新低"""
    entry_low = state_yesterday.get("building_entry_low")
    if entry_low is None:
        return False
    close = get_close(ind)
    if close < entry_low:
        return True
    return False


# ============================================================
# 状态机
# ============================================================

def compute_policy(
    signals_today: dict,
    state_yesterday: dict,
    etf_symbol: str,
    date: str,
    daily_raw: list = None
) -> dict:
    ind = signals_today.get("指标数据", {})
    momentum = signals_today.get("动能", "")
    params = load_params()
    pct_p80 = ind.get("Pct_P80", ind.get("pct_p80", 1.5))

    state = deepcopy(state_yesterday)
    state["symbol"] = etf_symbol
    state["pct_p80"] = pct_p80
    warn, exec_line = calc_stop_lines(pct_p80, params)
    state["stop_warn_line"] = warn
    state["stop_exec_line"] = exec_line

    current = state["trend_state"]

    def _make_result(**kwargs):
        result = {
            "trend_state": kwargs.get("trend_state", current),
            "action": kwargs.get("action", "NONE"),
            "position_level": kwargs.get("position_level", state.get("position_level", 0)),
            "target_weight": kwargs.get("target_weight", state.get("target_weight", 0)),
            "signal_strength": get_signal_strength(momentum),
            "reason": kwargs.get("reason", ""),
            "cooldown_left": kwargs.get("cooldown_left", 0),
            "price_factor": calc_price_factor(
                get_bias(ind), get_bias_max(ind), params.get("price_discount_factor", 0.5)
            ),
            "stop_warn_line": warn,
            "stop_exec_line": exec_line,
            "asOf": date
        }
        # update state
        state["trend_state"] = result["trend_state"]
        state["position_level"] = result["position_level"]
        state["target_weight"] = result["target_weight"]
        state["as_of"] = date

        hist_entry = {
            "date": date,
            "trend_state": result["trend_state"],
            "action": result["action"],
            "momentum": momentum,
            "position_level": result["position_level"],
            "reason": result["reason"]
        }
        append_history(state, date, hist_entry)
        return result

    # 止损检查
    if current in ("BUILDING", "IN"):
        stop = check_stop_loss(signals_today, ind, state)
        if stop:
            state["trend_state"] = "COOLING" if stop["action"] == "STOP_EXIT" else current
            state["position_level"] = stop["position_level"]
            state["target_weight"] = 0 if stop["action"] == "STOP_EXIT" else state["target_weight"]
            state["exit_reason"] = "stop_loss"
            state["exit_date"] = date
            return _make_result(
                trend_state=state["trend_state"],
                action=stop["action"],
                position_level=stop["position_level"],
                target_weight=state["target_weight"],
                reason=stop["reason"],
                cooldown_left=params.get("cooldown_min_days", 3) if stop["action"] == "STOP_EXIT" else 0
            )

    # OUT
    if current == "OUT":
        if check_entry_r1(signals_today, ind):
            first_ratio = params.get("first_entry_ratio", 0.6)
            state["entry_date"] = date
            state["exit_reason"] = None
            state["exit_date"] = None
            state["peak_equity"] = get_close(ind)
            return _make_result(
                trend_state="IN",
                action="ENTER",
                position_level=first_ratio,
                reason=f"趋势确认入场: 热度连升{ind.get('Amount_Share_DaysUp',0)}天, 动能:{momentum}"
            )

        if check_entry_r0(signals_today, ind) and check_entry_r0_new_lows(signals_today, ind, daily_raw):
            build_ratio = params.get("building_entry_ratio", 0.25)
            state["entry_date"] = date
            state["building_entry_low"] = min(
                d.get("low", d.get("close", 0)) for d in daily_raw[-5:]
            ) if daily_raw and len(daily_raw) >= 5 else get_close(ind)
            state["peak_equity"] = get_close(ind)
            return _make_result(
                trend_state="BUILDING",
                action="BUILD",
                position_level=build_ratio,
                reason=f"筑底试探: 阶段={signals_today.get('阶段信号','')}, Bias={get_bias(ind):.1f}%"
            )

        return _make_result(action="NONE", reason="无入场信号")

    # BUILDING
    if current == "BUILDING":
        if check_building_fail(signals_today, ind, state):
            state["exit_reason"] = "building_fail"
            state["exit_date"] = date
            return _make_result(
                trend_state="OUT",
                action="EXIT",
                position_level=0.0,
                target_weight=0.0,
                reason="筑底失败: 创新低, 清仓试探仓"
            )

        if check_entry_r1(signals_today, ind):
            first_ratio = params.get("first_entry_ratio", 0.6)
            state["building_entry_low"] = None
            state["peak_equity"] = max(state.get("peak_equity", 0), get_close(ind))
            return _make_result(
                trend_state="IN",
                action="ENTER",
                position_level=first_ratio,
                reason=f"筑底升级→趋势确认: 热度连升{ind.get('Amount_Share_DaysUp',0)}天, 动能:{momentum}"
            )

        exit_type = check_exit(signals_today, ind)
        if exit_type:
            state["exit_reason"] = exit_type
            state["exit_date"] = date
            return _make_result(
                trend_state="COOLING",
                action="EXIT",
                position_level=0.0,
                target_weight=0.0,
                reason=f"筑底中出场: {exit_type}",
                cooldown_left=params.get("cooldown_min_days", 3)
            )

        return _make_result(
            trend_state="BUILDING",
            action="HOLD",
            reason=f"筑底持有中, 阶段:{signals_today.get('阶段信号','')}"
        )

    # IN
    if current == "IN":
        state["peak_equity"] = max(state.get("peak_equity", 0), get_close(ind))

        topup_reason = check_topup(signals_today, ind, state)
        if topup_reason and state.get("position_level", 0) < 1.0:
            return _make_result(
                trend_state="IN",
                action="TOPUP",
                position_level=1.0,
                reason=topup_reason
            )

        cut = check_cut(signals_today, ind, state)
        if cut:
            return _make_result(
                trend_state="IN",
                action=cut["action"],
                position_level=cut["position_level"],
                reason=cut["reason"]
            )

        exit_type = check_exit(signals_today, ind)
        if exit_type:
            state["exit_reason"] = exit_type
            state["exit_date"] = date
            return _make_result(
                trend_state="COOLING",
                action="EXIT",
                position_level=0.0,
                target_weight=0.0,
                reason=_build_exit_reason(exit_type, signals_today, ind),
                cooldown_left=params.get("cooldown_min_days", 3)
            )

        return _make_result(
            trend_state="IN",
            action="HOLD",
            reason=f"持有中, 动能:{momentum}, 级别:{state.get('position_level',0)*100:.0f}%"
        )

    # COOLING
    if current == "COOLING":
        exit_date = state.get("exit_date", "")
        cooldown_days = _count_trading_days(exit_date, date)
        params_cooldown = params.get("cooldown_min_days", 3)
        remaining = max(0, params_cooldown - cooldown_days)

        if cooldown_days >= params_cooldown:
            release = check_cooldown_release(signals_today, ind, state)
            if release:
                state["exit_reason"] = None
                state["exit_date"] = None
                return _make_result(
                    trend_state="OUT",
                    action="NONE",
                    position_level=0.0,
                    target_weight=0.0,
                    reason=release.get("reason", "冷却解除"),
                    cooldown_left=0
                )

        return _make_result(
            trend_state="COOLING",
            action="NONE",
            position_level=0.0,
            target_weight=0.0,
            reason=f"冷却中, 还需{remaining}个交易日",
            cooldown_left=remaining
        )

    return _make_result(action="NONE", reason="未知状态")


def _build_exit_reason(exit_type: str, signals: dict, ind: dict) -> str:
    momentum = signals.get("动能", "")
    bias = get_bias(ind)
    if exit_type == "overheat":
        return f"过热清仓: Bias={bias:.1f}% ≥ 极值, 落袋为安"
    if exit_type == "trend_break":
        return f"趋势破坏清仓: 动能={momentum}"
    if exit_type == "stage_bad":
        return f"阶段转坏: {signals.get('阶段信号','')} / {signals.get('操作建议','')}"
    if exit_type == "panic":
        return "恐慌出逃清仓"
    if exit_type == "stop_loss":
        return "止损清仓"
    return f"清仓: {exit_type}"


def _count_trading_days(from_date: str, to_date: str) -> int:
    if not from_date or not to_date:
        return 0
    from datetime import date, timedelta
    try:
        d_from = date.fromisoformat(from_date)
        d_to = date.fromisoformat(to_date)
        count = 0
        current = d_from + timedelta(days=1)
        while current <= d_to:
            if current.weekday() < 5:
                count += 1
            current += timedelta(days=1)
        return count
    except Exception:
        return 0
