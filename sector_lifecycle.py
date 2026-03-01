from typing import List, Tuple, Optional, Dict, Any
from sector_lifecycle_config import (
    POSITION_STAGE_COMBOS,
    DEFAULT_COMBO,
    DEFAULT_THRESHOLDS,
    SECTOR_THRESHOLDS,
)
import pandas as pd


def calculate_alpha(sector_return: float, market_return: float) -> float:
    if market_return == 0:
        return sector_return
    return sector_return - market_return


def calculate_alpha_n_days(
    sector_data: List[Tuple[object, float]],
    market_data: List[Tuple[object, float]],
    days: int
) -> Optional[float]:
    if len(sector_data) < days + 1 or len(market_data) < days + 1:
        return None
    sector_recent = sector_data[-(days + 1):]
    market_recent = market_data[-(days + 1):]
    sector_base = sector_recent[0][1]
    market_base = market_recent[0][1]
    if sector_base == 0 or market_base == 0:
        return None
    sector_return = (sector_recent[-1][1] - sector_base) / sector_base
    market_return = (market_recent[-1][1] - market_base) / market_base
    return calculate_alpha(sector_return, market_return)


def calculate_amount_share(sector_amount: float, total_amount: float) -> float:
    if total_amount == 0:
        return 0
    return sector_amount / total_amount


def calculate_amount_share_ma5(history: List[float]) -> float:
    if len(history) < 5:
        return sum(history) / len(history) if history else 0
    return sum(history[-5:]) / 5


def detect_false_kill(
    sector_data: Dict[str, Any],
    market_breadth: Dict[str, Any],
    news_factor: Optional[Dict[str, Any]] = None
) -> bool:
    """
    错杀机会检测
    条件：
    1. 板块处于上升期（alpha_20 > 0 或 amount_share 处于高位）
    2. 大盘恐慌（下跌家数占比 > 65% 或 大盘跌幅 > 1%）
    3. 如有新闻因子：利空和板块无关
    """
    alpha_20 = sector_data.get("alpha_20", 0) or 0
    amount_share = sector_data.get("amount_share", 0) or 0
    amount_share_p80 = sector_data.get("amount_share_p80")
    sector_up = alpha_20 > 0
    if amount_share_p80 is not None:
        sector_up = sector_up or amount_share >= amount_share_p80

    down = market_breadth.get("down", 0) or 0
    total = market_breadth.get("total", 0) or 0
    if total <= 0:
        up = market_breadth.get("up", 0) or 0
        total = up + down
    panic_ratio = down / total if total > 0 else 0
    market_return = market_breadth.get("market_return", 0) or 0
    market_panic = panic_ratio > 0.65 or market_return <= -1

    news_irrelevant = True
    if news_factor is not None:
        news_irrelevant = not bool(news_factor.get("related_to_sector", False))

    return bool(sector_up and market_panic and news_irrelevant)


def determine_position(alpha_20: float, amount_share_ma5: float, sector_name: Optional[str] = None) -> dict:
    thresholds = SECTOR_THRESHOLDS.get(sector_name or "", DEFAULT_THRESHOLDS)
    alpha_high = thresholds["alpha_high"]
    alpha_mid = thresholds["alpha_mid"]
    alpha_low = thresholds["alpha_low"]
    amount_high = thresholds["amount_high"]
    amount_low = thresholds["amount_low"]

    if alpha_20 > alpha_high:
        if amount_share_ma5 > amount_high:
            return {"区域": "高位区", "位置": "过热期"}
        if amount_share_ma5 > amount_low:
            return {"区域": "高位区", "位置": "强势期"}
        return {"区域": "高位区", "位置": "背离期"}

    if alpha_20 > alpha_mid:
        if amount_share_ma5 > amount_high:
            return {"区域": "中位区", "位置": "热门期"}
        if amount_share_ma5 > amount_low:
            return {"区域": "中位区", "位置": "活跃期"}
        return {"区域": "高位区", "位置": "背离期"}

    if alpha_20 > alpha_low:
        if amount_share_ma5 > amount_high:
            return {"区域": "低位区", "位置": "补涨期"}
        if amount_share_ma5 > amount_low:
            return {"区域": "中位区", "位置": "中性期"}
        return {"区域": "中位区", "位置": "磨底期"}

    if amount_share_ma5 > amount_high:
        return {"区域": "异常区", "位置": "异常期"}
    if amount_share_ma5 > amount_low:
        return {"区域": "低位区", "位置": "弱势期"}
    return {"区域": "低位区", "位置": "冰点期"}


def determine_position_area(alpha_20: Optional[float], amount_share_ma5: float) -> str:
    a = (alpha_20 or 0) * 100
    s = amount_share_ma5 or 0
    if a > 8 and s > 0.40:
        return "高位区"
    if 3 <= a <= 8 and 0.25 <= s <= 0.40:
        return "中高位区"
    if -3 <= a <= 3 and 0.15 <= s <= 0.25:
        return "中位区"
    if a < -3 and 0.10 <= s <= 0.15:
        return "低位区"
    if a < -8 and s < 0.10:
        return "冰点区"
    if a > 8:
        return "高位区"
    if a > 3:
        return "中高位区"
    if a >= -3:
        return "中位区"
    if a >= -8:
        return "低位区"
    return "冰点区"


def determine_momentum(alpha_5: Optional[float], ma5_slope: float, close: float, ma5: float) -> str:
    a = (alpha_5 or 0) * 100
    above = close > ma5 if ma5 else False
    if a > 3 and ma5_slope > 0 and above:
        return "强势向上"
    if a > 3 and ma5_slope < 0 and not above:
        return "强势向下"
    if 1 <= a <= 3 and ma5_slope > 0 and above:
        return "偏强向上"
    if 1 <= a <= 3 and ma5_slope < 0 and not above:
        return "偏强向下"
    if -1 <= a <= 1:
        return "中性震荡"
    if a < -1 and ma5_slope < 0 and not above:
        return "弱势向下"
    if a < -1 and ma5_slope > 0 and above:
        return "弱势反弹"
    return "中性震荡" if above else "弱势向下"


def determine_fund_behavior(
    amount_share_pct: float,
    amount_share_change: Optional[float],
    amount_share_p80: Optional[float],
    amount_share_high_20: Optional[float],
    bias_20: float,
    pct: float
) -> str:
    if pct < -3 and amount_share_p80 is not None and amount_share_pct > amount_share_p80:
        return "恐慌出逃"
    if amount_share_change is not None and amount_share_change >= 0.5 and pct > 0:
        return "放量启动"
    if amount_share_high_20 is not None and amount_share_high_20 > 0:
        decline = (amount_share_high_20 - amount_share_pct) / amount_share_high_20
        if decline >= 0.20:
            return "资金撤退"
    if bias_20 > 8 and pct > 0:
        return "加速赶顶"
    if bias_20 < -8 and pct < 0:
        return "超跌反弹"
    return "横盘整理"


def determine_advice(momentum: str, behavior: str) -> str:
    if momentum == "强势向下":
        return "果断止损/观望"
    if momentum == "偏强向下":
        return "观望"
    if momentum == "弱势向下":
        if behavior == "恐慌出逃":
            return "坚决回避"
        if behavior == "资金撤退":
            return "空仓观望"
        if behavior == "横盘整理":
            return "观望等待"
        return "观望"
    if momentum == "弱势反弹":
        if behavior == "放量启动":
            return "关注企稳"
        if behavior == "横盘整理":
            return "等待确认"
        return "观望"
    if momentum == "中性震荡":
        if behavior == "放量启动":
            return "轻仓试探"
        if behavior == "横盘整理":
            return "小仓埋伏"
        if behavior == "资金撤退":
            return "观望"
        if behavior == "超跌反弹":
            return "关注企稳"
        return "观望"
    if momentum == "偏强向上":
        if behavior == "放量启动":
            return "积极建仓"
        if behavior == "横盘整理":
            return "持有"
        if behavior == "资金撤退":
            return "逐步减仓"
        if behavior == "加速赶顶":
            return "分批止盈"
        return "持有"
    if momentum == "强势向上":
        if behavior == "放量启动":
            return "持股待涨"
        if behavior == "加速赶顶":
            return "分批止盈"
        if behavior == "资金撤退":
            return "果断离场"
        if behavior == "恐慌出逃":
            return "果断离场"
        if behavior == "横盘整理":
            return "持有观察"
        if behavior == "超跌反弹":
            return "低吸机会"
        return "持有观察"
    return "观望"


def build_momentum_reason(momentum: str, alpha_5: Optional[float]) -> str:
    a = (alpha_5 or 0) * 100
    if momentum in ["强势向上", "偏强向上"]:
        return f"5日超额收益{a:+.1f}%（短期偏强）"
    if momentum == "强势向下":
        return f"5日超额收益{a:+.1f}%（短期转弱）"
    if momentum == "偏强向下":
        return f"5日超额收益{a:+.1f}%（上涨回调）"
    if momentum == "弱势向下":
        return f"5日超额收益{a:+.1f}%（趋势走弱）"
    if momentum == "弱势反弹":
        return f"5日超额收益{a:+.1f}%（弱势反弹）"
    return f"5日超额收益{a:+.1f}%（震荡）"


def build_behavior_reason(
    behavior: str,
    amount_share_change: Optional[float],
    amount_share_high_20: Optional[float],
    amount_share_pct: float,
    bias_20: float,
    pct: float
) -> str:
    if behavior == "放量启动":
        if amount_share_change is not None:
            return f"资金热度相对5日均值增长{amount_share_change * 100:.0f}%（放量进场）"
        return "资金热度显著提升（放量进场）"
    if behavior == "资金撤退":
        if amount_share_high_20 is not None and amount_share_high_20 > 0:
            decline = (amount_share_high_20 - amount_share_pct) / amount_share_high_20
            return f"资金热度较20日高点回落{decline * 100:.0f}%（资金撤退）"
        return "资金热度回落（资金撤退）"
    if behavior == "恐慌出逃":
        return f"当日涨跌{pct:+.1f}%，资金关注高位（恐慌出逃）"
    if behavior == "加速赶顶":
        return f"偏离均线{bias_20:.1f}%（加速赶顶）"
    if behavior == "超跌反弹":
        return f"偏离均线{bias_20:.1f}%（超跌反弹）"
    return "资金热度平稳（横盘整理）"


def build_bias_compare(
    bias_20: float,
    bias_20_history_max: Optional[float],
    bias_20_history_min: Optional[float]
) -> Optional[str]:
    if bias_20_history_max is None or bias_20_history_max == 0:
        return None
    if bias_20_history_min is None or bias_20_history_min == 0:
        return None
    return f"当前偏离 {bias_20:+.1f}%，历史极值 +{bias_20_history_max:.1f}% / {bias_20_history_min:.1f}%"


def determine_stage(
    close: float,
    ma20: float,
    ma60: float,
    bias_20: float,
    pct: float,
    amount_share: float,
    rs_change_20: float,
    ma20_slope: float = 0,
    ma60_slope: float = 0,
    high_20: float = None,
    rs_max_20: float = None,
    amount_share_high_20: float = None
) -> str:
    if close < ma20 and ma20 < ma60:
        return "衰退期"
    if high_20 and close >= high_20 * 0.995:
        if rs_max_20 and rs_change_20 < rs_max_20 * 0.7:
            return "背离期A"
    if amount_share_high_20 and amount_share_high_20 > 0:
        decline = (amount_share_high_20 - amount_share) / amount_share_high_20
        if decline >= 0.20:
            return "背离期B"
    if bias_20 >= 8 and ma20_slope > 0:
        return "加速期"
    if close > ma60 and ma60_slope > 0 and pct >= 2 and amount_share >= 0.6:
        return "启动期"
    if 2 <= bias_20 <= 5 and abs(ma20_slope) <= 0.2:
        return "震荡期"
    if close < ma60 and rs_change_20 >= -0.2 and amount_share <= 0.3:
        return "潜伏期"
    if close >= ma60:
        return "震荡期"
    return "潜伏期"


def get_combo_info(position: str, stage: str) -> dict:
    key = (position, stage)
    return POSITION_STAGE_COMBOS.get(key, DEFAULT_COMBO)


def select_dynamic_benchmark(
    sector_df: pd.DataFrame,
    benchmark_map: Dict[str, pd.DataFrame],
    days: int = 60
) -> Tuple[Optional[str], Optional[float]]:
    if sector_df is None or sector_df.empty or not benchmark_map:
        return None, None
    best_name = None
    best_corr = None
    for name, bench_df in benchmark_map.items():
        if bench_df is None or bench_df.empty:
            continue
        merged = pd.merge(
            sector_df[["date", "close"]],
            bench_df[["date", "close"]],
            on="date",
            how="inner",
            suffixes=("_sector", "_bench")
        )
        merged = merged.dropna()
        if merged.empty:
            continue
        if days:
            merged = merged.tail(days)
        if len(merged) < 2:
            continue
        corr = merged["close_sector"].corr(merged["close_bench"])
        if corr is None:
            continue
        if best_corr is None or corr > best_corr:
            best_corr = corr
            best_name = name
    return best_name, best_corr


def analyze_sector(
    sector_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    sector_name: str,
    benchmark_name: Optional[str] = None,
    benchmark_corr: Optional[float] = None,
    market_amount_df: Optional[pd.DataFrame] = None,
    history_df: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    alpha_5 = calculate_alpha_n_days(
        list(zip(sector_df["date"], sector_df["close"])),
        list(zip(benchmark_df["date"], benchmark_df["close"])) if benchmark_df is not None else [],
        days=5
    )
    alpha_20 = calculate_alpha_n_days(
        list(zip(sector_df["date"], sector_df["close"])),
        list(zip(benchmark_df["date"], benchmark_df["close"])) if benchmark_df is not None else [],
        days=20
    )

    amount_share = sector_df["amount"].iloc[-1] if len(sector_df) else 0
    amount_share_history = sector_df["amount"].tolist() if len(sector_df) else []

    total_amount = 0
    amount_share_series = []
    if market_amount_df is not None and not market_amount_df.empty and "amount" in market_amount_df.columns:
        merged_amount = pd.merge(
            sector_df[["date", "amount"]],
            market_amount_df[["date", "amount"]],
            on="date",
            how="inner",
            suffixes=("_sector", "_market")
        )
        merged_amount = merged_amount.dropna()
        for _, r in merged_amount.iterrows():
            total = r.get("amount_market", 0)
            sec = r.get("amount_sector", 0)
            if total and total > 0:
                amount_share_series.append(sec / total)
        if not merged_amount.empty:
            total_amount = merged_amount.iloc[-1].get("amount_market", 0)
    if total_amount == 0 and amount_share_history:
        total_amount = market_amount_df["amount"].iloc[-1] if market_amount_df is not None and "amount" in market_amount_df.columns and len(market_amount_df) else 0
    amount_share_pct = calculate_amount_share(amount_share, total_amount) if total_amount > 0 else 0
    amount_share_ma5_pct = calculate_amount_share_ma5(amount_share_series) if amount_share_series else amount_share_pct
    amount_share_change = amount_share_pct / amount_share_ma5_pct - 1 if amount_share_ma5_pct else None
    amount_share_p80 = None
    if amount_share_series:
        try:
            amount_share_p80 = float(pd.Series(amount_share_series).quantile(0.8))
        except:
            amount_share_p80 = None
    amount_share_high_20 = max(amount_share_series[-20:]) if amount_share_series else None

    ma5_series = sector_df["close"].rolling(5).mean() if len(sector_df) else pd.Series()
    ma20_series = sector_df["close"].rolling(20).mean() if len(sector_df) else pd.Series()
    ma60_series = sector_df["close"].rolling(60).mean() if len(sector_df) else pd.Series()
    ma5 = ma5_series.iloc[-1] if len(ma5_series) else 0
    ma20 = ma20_series.iloc[-1] if len(ma20_series) else 0
    ma60 = ma60_series.iloc[-1] if len(ma60_series) else 0
    if pd.isna(ma5):
        ma5 = 0
    if pd.isna(ma20):
        ma20 = 0
    if pd.isna(ma60):
        ma60 = 0
    close = sector_df["close"].iloc[-1] if len(sector_df) else 0
    bias_20 = (close - ma20) / ma20 * 100 if ma20 else 0

    ma5_slope = (ma5_series.iloc[-1] - ma5_series.iloc[-6]) / 5 if len(ma5_series) >= 6 else 0
    ma20_slope = (ma20_series.iloc[-1] - ma20_series.iloc[-6]) / 5 if len(ma20_series) >= 6 else 0
    ma60_slope = (ma60_series.iloc[-1] - ma60_series.iloc[-6]) / 5 if len(ma60_series) >= 6 else 0
    if pd.isna(ma5_slope):
        ma5_slope = 0
    if pd.isna(ma20_slope):
        ma20_slope = 0
    if pd.isna(ma60_slope):
        ma60_slope = 0

    bias_20_history_max = None
    bias_20_history_min = None
    if history_df is not None and not history_df.empty:
        history_df = history_df.copy()
        history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
        history_df = history_df.dropna(subset=["date"]).sort_values("date")
        history_df = history_df[history_df["date"] >= pd.to_datetime("2025-05-19")]
        if not history_df.empty:
            h_ma20 = history_df["close"].rolling(20).mean()
            h_bias = (history_df["close"] - h_ma20) / h_ma20 * 100
            h_bias = h_bias.dropna()
            if not h_bias.empty:
                bias_20_history_max = float(h_bias.max())
                bias_20_history_min = float(h_bias.min())

    position_info = determine_position(alpha_20 or 0, amount_share_ma5_pct, sector_name=sector_name)
    position_area = determine_position_area(alpha_20, amount_share_ma5_pct)

    stage = determine_stage(
        close=close,
        ma20=ma20,
        ma60=ma60,
        bias_20=bias_20,
        pct=sector_df["close"].pct_change().iloc[-1] * 100 if len(sector_df) > 1 else 0,
        amount_share=amount_share_pct,
        rs_change_20=alpha_20 or 0,
        ma20_slope=ma20_slope,
        ma60_slope=ma60_slope,
        high_20=sector_df["close"].rolling(20).max().iloc[-1] if len(sector_df) else None,
        rs_max_20=max(alpha_20 or 0, 0.1),
        amount_share_high_20=amount_share_high_20 if amount_share_high_20 is not None else amount_share_pct
    )

    combo_info = get_combo_info(position_info["位置"], stage)
    pct_val = sector_df["close"].pct_change().iloc[-1] * 100 if len(sector_df) > 1 else 0
    momentum = determine_momentum(alpha_5, ma5_slope, close, ma5)
    behavior = determine_fund_behavior(
        amount_share_pct=amount_share_pct,
        amount_share_change=amount_share_change,
        amount_share_p80=amount_share_p80,
        amount_share_high_20=amount_share_high_20,
        bias_20=bias_20,
        pct=pct_val
    )
    advice = determine_advice(momentum, behavior)
    momentum_reason = build_momentum_reason(momentum, alpha_5)
    behavior_reason = build_behavior_reason(
        behavior,
        amount_share_change,
        amount_share_high_20,
        amount_share_pct,
        bias_20,
        pct_val
    )
    attribution = f"以{benchmark_name}为基准，{momentum_reason}，{behavior_reason}。" if benchmark_name else f"{momentum_reason}，{behavior_reason}。"
    bias_compare = build_bias_compare(bias_20, bias_20_history_max, bias_20_history_min)

    return {
        "板块名称": sector_name,
        "基准指数": benchmark_name,
        "相关性": round(float(benchmark_corr), 4) if benchmark_corr is not None else None,
        "板块位置": position_area,
        "动能": momentum,
        "资金行为": behavior,
        "位置区域": position_info["区域"],
        "位置名称": position_info["位置"],
        "阶段信号": stage,
        "显示名称": combo_info["显示名称"],
        "含义": combo_info["含义"],
        "操作建议": advice,
        "归因说明": attribution,
        "乖离对比": bias_compare,
        "指标数据": {
            "Alpha_5": round(alpha_5, 4) if alpha_5 is not None else None,
            "Alpha_20": round(alpha_20, 4) if alpha_20 is not None else None,
            "Amount_Share": round(amount_share_pct, 4),
            "Amount_Share_MA5": round(amount_share_ma5_pct, 4),
            "Amount_Share_Change": round(amount_share_change, 4) if amount_share_change is not None and not pd.isna(amount_share_change) else None,
            "MA5": round(ma5, 2) if ma5 else 0,
            "MA20": round(ma20, 2) if ma20 else 0,
            "MA60": round(ma60, 2) if ma60 else 0,
            "MA5_Slope": round(ma5_slope, 4) if ma5_slope else 0,
            "MA60_Slope": round(ma60_slope, 4) if ma60_slope else 0,
            "Bias_20": round(bias_20, 2),
            "Bias_20_History_Max": round(bias_20_history_max, 2) if bias_20_history_max is not None else None,
            "Bias_20_History_Min": round(bias_20_history_min, 2) if bias_20_history_min is not None else None,
            "Pct": round(pct_val, 2),
            "alpha_5": round(alpha_5 * 100, 2) if alpha_5 is not None else None,
            "alpha_20": round(alpha_20 * 100, 2) if alpha_20 is not None else None,
            "amount_share": round(amount_share_pct * 100, 2),
            "amount_share_ma5": round(amount_share_ma5_pct * 100, 2),
            "ma20": round(ma20, 2) if ma20 else 0,
            "ma60": round(ma60, 2) if ma60 else 0,
            "bias_20": round(bias_20, 2),
            "close": round(close, 2),
            "pct": round(pct_val, 2)
        }
    }
