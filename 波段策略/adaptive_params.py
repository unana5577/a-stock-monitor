"""
自适应校准层
============
每只ETF维护"影子持有账户", 每日对比策略P&L vs 持有P&L,
自动调整震荡期交易参数, 让策略自适应当前行情。

策略领先持有 → 收紧阈值 (多交易, 赚网格)
策略落后持有 → 放宽阈值 (少交易, 接近持有)

方向感知: 主升/启动期只放宽不收紧(趋势中交易永远比持有差)
          下跌/防守期不校准(用默认参数)
"""
from typing import Dict

DEFAULT_PARAMS = {
    "sell_trigger_pct": 5.0,
    "buy_trigger_pct":  3.0,
    "sell_ratio":       0.10,
    "find_range":       1.0,
    "find_pct_max":     8.0,
}

BOUNDS = {
    "sell_trigger_pct": (3.0, 12.0),
    "buy_trigger_pct":  (2.0, 8.0),
    "sell_ratio":       (0.04, 0.20),
    "find_range":       (0.5, 5.0),
    "find_pct_max":     (5.0, 15.0),
}

CALIBRATE_COOLDOWN = 5
LAG_THRESHOLD  = 1.0

# 只在主升期校准
CALIBRATE_STAGE = "主升"


def init_shadow(pos, px: float):
    """初始化影子持有账户: 从总预算全仓买入"""
    pos.shadow_shares = int(pos.total / px / 100) * 100
    pos.shadow_cost = pos.shadow_shares * px


def shadow_pnl(pos, px: float) -> float:
    """影子持有账户的盈亏"""
    if pos.shadow_shares <= 0:
        return 0.0
    return pos.shadow_shares * px - pos.shadow_cost


def strategy_pnl(pos, px: float) -> float:
    """策略账户的盈亏"""
    return pos.equity(px) - pos.total


def calibrate(pos, px: float, stage: str = ""):
    """只在主升期校准: 策略落后持有→放宽卖出阈值, 防止过早止盈。其他阶段不校准。"""
    if pos.calibrate_cooldown > 0:
        pos.calibrate_cooldown -= 1
        return None

    if stage != CALIBRATE_STAGE:
        return None

    sp = strategy_pnl(pos, px)
    hp = shadow_pnl(pos, px)
    if pos.total <= 0:
        return None

    diff = (sp - hp) / pos.total * 100

    if diff <= -LAG_THRESHOLD:
        _loosen(pos)
        pos.calibrate_cooldown = CALIBRATE_COOLDOWN
        return f"主升期 策略落后{diff:+.1f}% 放宽卖出: sell={pos.params['sell_trigger_pct']:.0f}% sRatio={pos.params['sell_ratio']:.2f}"

    return None


def _tighten(pos):
    """收紧阈值 — 更容易触发交易"""
    p = pos.params
    p["sell_trigger_pct"] = _clamp(p["sell_trigger_pct"] - 0.5, "sell_trigger_pct")
    p["buy_trigger_pct"]  = _clamp(p["buy_trigger_pct"] - 0.5, "buy_trigger_pct")
    p["sell_ratio"]       = _clamp(p["sell_ratio"] + 0.02, "sell_ratio")
    p["find_range"]       = _clamp(p["find_range"] - 0.3, "find_range")
    p["find_pct_max"]     = _clamp(p["find_pct_max"] - 1.0, "find_pct_max")


def _loosen(pos):
    """放宽阈值 — 更难触发交易, 接近持有"""
    p = pos.params
    p["sell_trigger_pct"] = _clamp(p["sell_trigger_pct"] + 1.0, "sell_trigger_pct")
    p["buy_trigger_pct"]  = _clamp(p["buy_trigger_pct"] + 1.0, "buy_trigger_pct")
    p["sell_ratio"]       = _clamp(p["sell_ratio"] - 0.02, "sell_ratio")
    p["find_range"]       = _clamp(p["find_range"] + 0.5, "find_range")
    p["find_pct_max"]     = _clamp(p["find_pct_max"] + 2.0, "find_pct_max")


def _clamp(val: float, key: str) -> float:
    lo, hi = BOUNDS[key]
    return max(lo, min(hi, val))
