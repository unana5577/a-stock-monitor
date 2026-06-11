"""
四阶段子策略执行器
==================
R1-R4:  震荡期 (网格波段)
R5-R6:  启动期 (试探+确认)
R7-R8:  主升期 (趋势持有)
R9-R10: 防守期 (空仓等待)

每个ETF独立维护状态, 由外层的阶段判断器驱动。
"""
from typing import Dict, Optional, List, Tuple
from stage_detector import (
    STAGE_RANGED, STAGE_STARTUP, STAGE_UPTREND, STAGE_DECLINING, STAGE_DEFENSE
)
from adaptive_params import DEFAULT_PARAMS, init_shadow, calibrate, shadow_pnl, strategy_pnl


class PositionState:
    """单只ETF的持仓状态"""

    def __init__(self, symbol: str, total_budget: float = 100_000):
        self.symbol = symbol
        self.total = total_budget
        self.base_shares = 0
        self.base_cost = 0.0
        self.swing_lots: List[dict] = []   # [{shares, cost, entry_date}]
        self.cash = total_budget
        self.stage = STAGE_RANGED
        self.entry_peak = 0.0              # 启动/主升入场后最高价
        self.build_phase = 0               # 震荡期建仓批次数 (0~3)
        self.last_action = None            # 'BUY' | 'SELL' | 'FIND' | 'HOLD'
        self.last_action_day = ""
        self.find_cooldown = 0            # 找底加仓后禁止卖出天数
        self.sell_cooldown = 0            # 卖出后禁止买入天数
        self.buy_cooldown = 0             # 买入后禁止再买天数
        self.params = dict(DEFAULT_PARAMS)  # 动态参数(校准层更新)
        self.shadow_shares = 0            # 影子持有账户股数
        self.shadow_cost = 0.0            # 影子持有账户成本
        self.calibrate_cooldown = 0       # 校准冷却天数
        self._params_reset_for_trend = "" # 标记趋势参数重置

    @property
    def total_shares(self) -> int:
        return self.base_shares + sum(l["shares"] for l in self.swing_lots)

    def total_value(self, price: float) -> float:
        return self.total_shares * price

    def equity(self, price: float) -> float:
        return self.cash + self.total_value(price)

    @property
    def base_cost_or_price(self) -> float:
        return self.base_cost if self.base_cost > 0 else 1.0

    def position_pct(self, price: float) -> float:
        eq = self.equity(price)
        return self.total_value(price) / eq if eq > 0 else 0

    def pct_change(self, price: float) -> float:
        return (price - self.base_cost_or_price) / self.base_cost_or_price * 100


def execute_day(pos: PositionState, stage: str, price: float, day: str, diag: dict = None) -> List[dict]:
    """单日执行子策略, 返回当日产生的交易列表 [{type, action, shares, price, note}]"""
    trades = []
    pos.stage = stage
    if pos.find_cooldown > 0:
        pos.find_cooldown -= 1
    if pos.sell_cooldown > 0:
        pos.sell_cooldown -= 1
    if pos.buy_cooldown > 0:
        pos.buy_cooldown -= 1

    # 进入趋势阶段: 重置参数(趋势中交易越少越好)
    if stage in (STAGE_UPTREND, STAGE_STARTUP) and pos._params_reset_for_trend != stage:
        pos.params = dict(DEFAULT_PARAMS)
        pos._params_reset_for_trend = stage
    elif stage not in (STAGE_UPTREND, STAGE_STARTUP):
        pos._params_reset_for_trend = ""

    if stage == STAGE_RANGED:
        trades = _execute_ranged(pos, price, day, diag)
    elif stage == STAGE_STARTUP:
        trades = _execute_startup(pos, price, day)
    elif stage == STAGE_UPTREND:
        trades = _execute_uptrend(pos, price, day)
    elif stage == STAGE_DECLINING:
        trades = _execute_declining(pos, price, day)
    elif stage == STAGE_DEFENSE:
        trades = _execute_defense(pos, price, day)

    if trades:
        for t in trades:
            t["date"] = day
        pos.last_action = trades[-1]["action"] if trades[-1]["action"] != "HOLD" else pos.last_action
        pos.last_action_day = day

    return trades


# ============================================================
# R1-R4: 震荡期
# ============================================================
def _execute_ranged(pos: PositionState, px: float, day: str, diag: dict = None) -> List[dict]:
    trades = []
    cd_ok = True
    ma20_above_ma60 = diag and diag.get("ma20") and diag.get("ma60") and diag["ma20"] > diag["ma60"]

    # --- R1: 分批建底仓 ---
    if pos.build_phase < 3:
        batch_target = pos.total * 0.70 / 3
        bs = int(batch_target / px / 100) * 100
        if bs >= 100 and pos.cash >= bs * px:
            pos.cash -= bs * px
            ns = pos.base_shares + bs
            pos.base_cost = ((pos.base_shares * pos.base_cost + bs * px) / ns) if ns > 0 else px
            pos.base_shares = ns
            pos.build_phase += 1
            trades.append({"type": "建仓", "action": "BUY", "shares": bs, "price": round(px, 4),
                "note": f"震荡底仓{pos.build_phase}/3 均价{pos.base_cost:.4f}"})
            pos.buy_cooldown = 1
        return trades

    # --- R2: 横盘找底加仓 (MA20>MA60多头 + 回踩MA20 + 浮盈<8% + 卖后冷却) ---
    if ma20_above_ma60 and diag and pos.position_pct(px) < 0.85 and pos.sell_cooldown <= 0 and pos.buy_cooldown <= 0:
        ma20 = diag["ma20"]
        pct_from_ma20 = (px - ma20) / ma20 * 100 if ma20 > 0 else 0
        pct = pos.pct_change(px)
        fr = pos.params["find_range"]
        fp = pos.params["find_pct_max"]
        if -fr <= pct_from_ma20 <= fr and pct < fp:
            add_val = pos.total * 0.10
            bs = int(add_val / px / 100) * 100
            if bs >= 100 and pos.cash >= bs * px:
                pos.cash -= bs * px
                pos.swing_lots.append({"shares": bs, "cost": px, "entry_date": day})
                trades.append({"type": "找底加仓", "action": "BUY", "shares": bs, "price": round(px, 4),
                    "note": f"回踩MA20({ma20:.4f}) 偏离{pct_from_ma20:+.1f}% 加仓{bs}股 花费{bs*px:.0f}"})
                pos.find_cooldown = 1
                pos.buy_cooldown = 1
                return trades

    # --- R3: 盈利套利 ---
    pct = pos.pct_change(px)
    st = pos.params["sell_trigger_pct"]
    sr = pos.params["sell_ratio"]
    if pct >= st and pos.total_shares > 0 and pos.last_action != "SELL" and pos.find_cooldown <= 0 and cd_ok:
        sv = pos.total_value(px) * sr
        ss = int(sv / px / 100) * 100
        if ss >= 100:
            _sell_from_position(pos, ss, px)
            trades.append({"type": "套利", "action": "SELL", "shares": ss, "price": round(px, 4),
                "note": f"浮盈{pct:+.1f}%≥{st:.0f}% 卖出{ss}股 回笼{ss*px:.0f}"})
            pos.sell_cooldown = 1
            return trades

    # --- R4: 回调吸筹 ---
    bt = pos.params["buy_trigger_pct"]
    if pct <= -bt and pos.total_shares > 0 and pos.sell_cooldown <= 0 and pos.buy_cooldown <= 0 and cd_ok:
        bv = pos.total * 0.10
        bs = int(bv / px / 100) * 100
        if bs >= 100 and pos.cash >= bs * px and pos.position_pct(px) < 0.85:
            pos.cash -= bs * px
            pos.swing_lots.append({"shares": bs, "cost": px, "entry_date": day})
            trades.append({"type": "吸筹", "action": "BUY", "shares": bs, "price": round(px, 4),
                "note": f"浮亏{pct:+.1f}%≤{-bt:.0f}% 买入{bs}股 花费{bs*px:.0f}"})
            pos.buy_cooldown = 1
            return trades

    return trades


# ============================================================
# R5-R6: 启动期
# ============================================================
def _execute_startup(pos: PositionState, px: float, day: str) -> List[dict]:
    trades = []

    # --- R5: 试探建仓 30% ---
    if pos.total_shares == 0 and pos.build_phase < 3:
        target_val = pos.total * 0.30
        bs = int(target_val / px / 100) * 100
        if bs >= 100 and pos.cash >= bs * px:
            pos.cash -= bs * px
            pos.base_cost = px
            pos.base_shares = bs
            pos.entry_peak = px
            pos.build_phase = 1
            trades.append({"type": "试探", "action": "BUY", "shares": bs, "price": round(px, 4),
                "note": f"启动试探建仓30% {bs}股@{px:.4f} 均价{px:.4f}"})
            return trades

    # 已有仓位, 跟踪最高价
    if px > pos.entry_peak:
        pos.entry_peak = px

    # --- R6: 突破加仓到70% ---
    if pos.total_shares > 0 and pos.position_pct(px) < 0.70:
        if px > pos.entry_peak * 1.02:
            target_val = pos.total * 0.70
            current_val = pos.total_value(px)
            need = target_val - current_val
            if need > 0:
                bs = int(need / px / 100) * 100
                if bs >= 100 and pos.cash >= bs * px:
                    pos.cash -= bs * px
                    ns = pos.base_shares + bs
                    pos.base_cost = ((pos.base_shares * pos.base_cost + bs * px) / ns) if ns > 0 else px
                    pos.base_shares = ns
                    pos.build_phase = 2
                    trades.append({"type": "加仓", "action": "BUY", "shares": bs, "price": round(px, 4),
                        "note": f"突破确认+2% 加仓至60% 均价{pos.base_cost:.4f}"})
                    return trades

    return trades


# ============================================================
# R7-R8: 主升期
# ============================================================
def _execute_uptrend(pos: PositionState, px: float, day: str) -> List[dict]:
    trades = []

    # R7: 牛末止损 — 阶段判定触发, 不需要在此处理(由backtest降级处理)

    # R8: 逐步加仓到80%
    if pos.position_pct(px) < 0.80 and pos.build_phase < 3:
        target_val = pos.total * 0.80
        current_val = pos.total_value(px)
        need = target_val - current_val
        step_val = pos.total * 0.10
        add_val = min(need, step_val)
        if add_val > 0:
            bs = int(add_val / px / 100) * 100
            if bs >= 100 and pos.cash >= bs * px:
                pos.cash -= bs * px
                ns = pos.base_shares + bs
                pos.base_cost = ((pos.base_shares * pos.base_cost + bs * px) / ns) if ns > 0 else px
                pos.base_shares = ns
                pos.build_phase = 3
                trades.append({"type": "趋势加仓", "action": "BUY", "shares": bs, "price": round(px, 4),
                    "note": f"主升加仓至80% 均价{pos.base_cost:.4f}"})
                return trades

    return trades


# ============================================================
# R9-R10: 下跌期
# ============================================================
def _execute_declining(pos: PositionState, px: float, day: str) -> List[dict]:
    trades = []

    # R9: 减仓到30%
    if pos.position_pct(px) > 0.30 and pos.total_shares > 0:
        target_val = pos.total * 0.30
        current_val = pos.total_value(px)
        excess_val = current_val - target_val
        sell_shares = int(excess_val / px / 100) * 100
        if sell_shares >= 100:
            _sell_from_position(pos, sell_shares, px)
            trades.append({"type": "转弱减仓", "action": "SELL", "shares": sell_shares,
                "price": round(px, 4),
                "note": f"下跌期减至30% 卖出{sell_shares}股 回笼{sell_shares*px:.0f}"})
            pos.sell_cooldown = 1
            return trades

    # R10: 持有30%等待修复或死叉
    return trades


# ============================================================
# R9-R10: 防守期
# ============================================================
def _execute_defense(pos: PositionState, px: float, day: str) -> List[dict]:
    trades = []

    # --- R9: 清仓等待 ---
    if pos.total_shares > 0:
        ts = pos.total_shares
        pos.cash += ts * px
        trades.append({"type": "防守清仓", "action": "SELL", "shares": ts, "price": round(px, 4),
            "note": f"进入防守, 清仓{ts}股 回笼{ts*px:.0f} 现金{pos.cash:.0f}"})
        pos.base_shares = 0
        pos.base_cost = 0.0
        pos.swing_lots = []
        pos.build_phase = 0
        pos.entry_peak = 0.0
        return trades

    return trades


# ============================================================
# 辅助
# ============================================================
def _sell_from_position(pos: PositionState, target_shares: int, px: float):
    """卖出target_shares股, 优先出波段仓"""
    rem = target_shares
    if pos.swing_lots:
        new_lots = []
        for lot in pos.swing_lots:
            ls = lot["shares"]
            if rem > 0 and ls > 0:
                taken = min(rem, ls)
                rem -= taken
                if ls > taken:
                    new_lots.append({"shares": ls - taken, "cost": lot["cost"],
                                     "entry_date": lot.get("entry_date", "")})
            else:
                new_lots.append(lot)
        pos.swing_lots = new_lots
    if rem > 0 and pos.base_shares > 0:
        pos.base_shares = max(0, pos.base_shares - rem)
    pos.cash += target_shares * px
