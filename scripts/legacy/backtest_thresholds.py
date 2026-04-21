#!/usr/bin/env python3
"""
板块生命周期系统 - 阈值回测脚本

目标：
1. 遍历历史数据，验证各阈值的预测准确率
2. 输出最优阈值建议
"""

import os
import sys
import json
import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from sector_lifecycle import (
    determine_position,
    determine_position_area,
    determine_momentum,
    determine_fund_behavior,
    determine_advice,
    detect_false_kill,
    calculate_alpha_n_days,
    calculate_amount_share,
    calculate_amount_share_ma5
)
from sector_lifecycle_config import DEFAULT_THRESHOLDS, SECTOR_THRESHOLDS

# 加载环境变量
def load_env():
    env_path = os.path.expanduser("~/.openclaw/workspace/.env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

load_env()

def load_sentiment_dataframe(file_path: Optional[str], value_columns: List[str], prefix: str) -> pd.DataFrame:
    """读取情绪数据 JSON 为 DataFrame（date + columns）。"""
    if not file_path or not os.path.exists(file_path):
        return pd.DataFrame(columns=["date"] + [f"{prefix}_{c}" for c in value_columns])

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print(f"警告: 读取情绪数据失败 {file_path}: {e}")
        return pd.DataFrame(columns=["date"] + [f"{prefix}_{c}" for c in value_columns])

    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not records:
        return pd.DataFrame(columns=["date"] + [f"{prefix}_{c}" for c in value_columns])

    rows = []
    for r in records:
        if not isinstance(r, dict):
            continue
        d = pd.to_datetime(r.get("date"), errors="coerce")
        if pd.isna(d):
            continue
        item = {"date": d}
        for c in value_columns:
            item[f"{prefix}_{c}"] = r.get(c)
        rows.append(item)

    if not rows:
        return pd.DataFrame(columns=["date"] + [f"{prefix}_{c}" for c in value_columns])
    return pd.DataFrame(rows).sort_values("date")


def load_market_sentiment_data(
    northbound_path: Optional[str] = "data/northbound_flow.json",
    margin_path: Optional[str] = "data/margin_balance.json",
    breadth_path: Optional[str] = "data/market_breadth.json"
) -> pd.DataFrame:
    """加载并合并北向资金、融资余额、涨跌家数。"""
    northbound_df = load_sentiment_dataframe(northbound_path, ["net_inflow"], "northbound")
    margin_df = load_sentiment_dataframe(
        margin_path,
        ["sse_margin_balance", "szse_margin_balance", "total_margin_balance"],
        "margin"
    )
    breadth_df = load_sentiment_dataframe(breadth_path, ["up", "down", "flat", "total"], "breadth")

    out = pd.DataFrame(columns=["date"])
    for d in [northbound_df, margin_df, breadth_df]:
        if d.empty:
            continue
        out = d.copy() if out.empty else out.merge(d, on="date", how="outer")
    if out.empty:
        return out
    return out.sort_values("date").reset_index(drop=True)


def get_trading_days(df: pd.DataFrame) -> List[str]:
    """获取所有交易日"""
    if "date" not in df.columns:
        return []
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.sort_values("date")
    return df["date"].dt.strftime("%Y-%m-%d").unique().tolist()


def calculate_metrics_at_date(
    sector_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    market_amount_df: pd.DataFrame,
    date: str,
    sector_name: Optional[str] = None
) -> Optional[Dict]:
    """计算某个日期的所有指标"""
    
    # 筛选到该日期为止的数据
    date_dt = pd.to_datetime(date)
    sector_cut = sector_df[sector_df["date"] <= date_dt].copy()
    benchmark_cut = benchmark_df[benchmark_df["date"] <= date_dt].copy()
    
    if len(sector_cut) < 60 or len(benchmark_cut) < 60:
        return None
    
    # 计算Alpha
    alpha_5 = calculate_alpha_n_days(
        list(zip(sector_cut["date"], sector_cut["close"])),
        list(zip(benchmark_cut["date"], benchmark_cut["close"])),
        days=5
    )
    alpha_20 = calculate_alpha_n_days(
        list(zip(sector_cut["date"], sector_cut["close"])),
        list(zip(benchmark_cut["date"], benchmark_cut["close"])),
        days=20
    )
    
    # 计算成交额占比
    merged = pd.merge(
        sector_cut[["date", "amount"]],
        market_amount_df[["date", "amount"]],
        on="date",
        how="inner",
        suffixes=("_sector", "_market")
    )
    amount_share_series = []
    for _, r in merged.iterrows():
        total = r.get("amount_market", 0)
        sec = r.get("amount_sector", 0)
        if total and total > 0:
            amount_share_series.append(sec / total)
    
    amount_share_pct = amount_share_series[-1] if amount_share_series else 0
    amount_share_ma5_pct = calculate_amount_share_ma5(amount_share_series) if amount_share_series else 0
    amount_share_change = amount_share_pct / amount_share_ma5_pct - 1 if amount_share_ma5_pct else None
    
    # 计算历史80分位
    amount_share_p80 = None
    if amount_share_series:
        try:
            amount_share_p80 = float(pd.Series(amount_share_series).quantile(0.8))
        except:
            pass
    
    amount_share_high_20 = max(amount_share_series[-20:]) if len(amount_share_series) >= 20 else None
    
    # 计算均线
    ma5_series = sector_cut["close"].rolling(5).mean()
    ma20_series = sector_cut["close"].rolling(20).mean()
    ma5 = ma5_series.iloc[-1] if len(ma5_series) else 0
    ma20 = ma20_series.iloc[-1] if len(ma20_series) else 0
    close = sector_cut["close"].iloc[-1]
    
    # 偏离度
    bias_20 = (close - ma20) / ma20 * 100 if ma20 else 0
    
    # 均线斜率
    ma5_slope = (ma5_series.iloc[-1] - ma5_series.iloc[-6]) / 5 if len(ma5_series) >= 6 else 0
    if pd.isna(ma5_slope):
        ma5_slope = 0
    
    # 当日涨跌幅
    pct = sector_cut["close"].pct_change().iloc[-1] * 100 if len(sector_cut) > 1 else 0
    
    # 判断
    position_info = determine_position(alpha_20 or 0, amount_share_ma5_pct, sector_name=sector_name)
    position = position_info["位置"]
    momentum = determine_momentum(alpha_5, ma5_slope, close, ma5)
    behavior = determine_fund_behavior(
        amount_share_pct=amount_share_pct,
        amount_share_change=amount_share_change,
        amount_share_p80=amount_share_p80,
        amount_share_high_20=amount_share_high_20,
        bias_20=bias_20,
        pct=pct
    )
    advice = determine_advice(momentum, behavior)
    
    return {
        "date": date,
        "alpha_5": alpha_5,
        "alpha_20": alpha_20,
        "amount_share_ma5_pct": amount_share_ma5_pct,
        "position": position,
        "position_area": position_info["区域"],
        "momentum": momentum,
        "behavior": behavior,
        "advice": advice,
        "close": close
    }


def calculate_future_return(
    sector_df: pd.DataFrame,
    date: str,
    days: int = 5
) -> Optional[float]:
    """计算未来N日的涨跌幅"""
    sector_df = sector_df.copy()
    sector_df["date"] = pd.to_datetime(sector_df["date"], errors="coerce")
    sector_df = sector_df.dropna(subset=["date"]).sort_values("date")
    
    date_dt = pd.to_datetime(date)
    future_df = sector_df[sector_df["date"] > date_dt].head(days)
    
    if len(future_df) < days:
        return None
    
    current_close = sector_df[sector_df["date"] == date_dt]["close"].values
    if len(current_close) == 0:
        return None
    
    current_close = current_close[0]
    future_close = future_df["close"].iloc[-1]
    
    return (future_close - current_close) / current_close * 100


def classify_advice(advice: str) -> str:
    """分类建议为 long / avoid / neutral"""
    if any(k in advice for k in ["持股", "建仓", "持有", "低吸", "埋伏", "试探", "关注企稳"]):
        return "long"
    if any(k in advice for k in ["止损", "离场", "回避", "空仓", "减仓", "止盈"]):
        return "avoid"
    return "neutral"


def summarize_returns(returns: List[float]) -> Dict:
    if not returns:
        return {
            "count": 0,
            "avg": 0.0,
            "median": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "payoff_ratio": None,
            "p25": 0.0,
            "p75": 0.0
        }
    arr = np.array(returns, dtype=float)
    pos = arr[arr > 0]
    neg = arr[arr <= 0]
    avg_loss = float(np.mean(neg)) if len(neg) else 0.0
    payoff = None
    if avg_loss < 0:
        avg_win = float(np.mean(pos)) if len(pos) else 0.0
        payoff = abs(avg_win / avg_loss) if avg_loss != 0 else None
    else:
        avg_win = float(np.mean(pos)) if len(pos) else 0.0
    return {
        "count": int(len(arr)),
        "avg": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr, ddof=0)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "win_rate": float(np.mean(arr > 0)),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "payoff_ratio": payoff,
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75))
    }


def classify_signal(
    advice: str,
    is_false_kill: bool,
    alpha_20: float,
    behavior: str
) -> str:
    """
    四类信号分类：
    - long: 正常做多
    - avoid: 真回避（板块下跌 + 利空相关，用行为代理）
    - false_kill: 错杀机会（特殊 long）
    - neutral: 观望
    """
    if is_false_kill:
        return "false_kill"

    action = classify_advice(advice)
    if action == "avoid":
        # 暂无新闻相关性数据，使用行为代理“利空相关”
        if alpha_20 <= 0 and behavior in ["恐慌出逃", "资金撤退"]:
            return "avoid"
        return "neutral"
    return action


def backtest_sector(
    sector_name: str,
    sector_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    market_amount_df: pd.DataFrame,
    market_sentiment_df: Optional[pd.DataFrame] = None,
    start_date: Optional[str] = None,
    horizon: int = 5
) -> Dict:
    """回测单个板块"""
    
    sector_df = sector_df.copy()
    benchmark_df = benchmark_df.copy()
    market_amount_df = market_amount_df.copy()

    sector_df["date"] = pd.to_datetime(sector_df["date"], errors="coerce")
    benchmark_df["date"] = pd.to_datetime(benchmark_df["date"], errors="coerce")
    market_amount_df["date"] = pd.to_datetime(market_amount_df["date"], errors="coerce")

    sector_df = sector_df.dropna(subset=["date"]).sort_values("date")
    benchmark_df = benchmark_df.dropna(subset=["date"]).sort_values("date")
    market_amount_df = market_amount_df.dropna(subset=["date"]).sort_values("date")

    base = sector_df[["date", "close", "amount"]].copy()
    bench = benchmark_df[["date", "close"]].copy().rename(columns={"close": "benchmark_close"})
    market = market_amount_df[["date", "amount"]].copy().rename(columns={"amount": "amount_market"})

    df = base.merge(bench, on="date", how="inner").merge(market, on="date", how="inner")
    if market_sentiment_df is not None and not market_sentiment_df.empty:
        sentiment_df = market_sentiment_df.copy()
        sentiment_df["date"] = pd.to_datetime(sentiment_df["date"], errors="coerce")
        sentiment_df = sentiment_df.dropna(subset=["date"])
        df = df.merge(sentiment_df, on="date", how="left")
    df = df.sort_values("date").reset_index(drop=True)

    if df.empty:
        return {
            "sector": sector_name,
            "total_samples": 0,
            "advice_stats": {},
            "action_stats": {},
            "overall_returns": {},
            "results": []
        }

    # 计算指标（向量化）
    df["amount_share"] = df["amount"] / df["amount_market"]
    df["amount_share_ma5"] = df["amount_share"].rolling(5).mean()
    df["amount_share_change"] = df["amount_share"] / df["amount_share_ma5"] - 1
    df["amount_share_p80"] = df["amount_share"].expanding().quantile(0.8)
    df["amount_share_high_20"] = df["amount_share"].rolling(20).max()

    df["ma5"] = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["bias_20"] = (df["close"] - df["ma20"]) / df["ma20"] * 100
    df["ma5_slope"] = (df["ma5"] - df["ma5"].shift(5)) / 5
    df["pct"] = df["close"].pct_change() * 100

    df["alpha_5"] = (df["close"] / df["close"].shift(5) - 1) - (
        df["benchmark_close"] / df["benchmark_close"].shift(5) - 1
    )
    df["alpha_20"] = (df["close"] / df["close"].shift(20) - 1) - (
        df["benchmark_close"] / df["benchmark_close"].shift(20) - 1
    )
    df["benchmark_pct"] = df["benchmark_close"].pct_change() * 100

    df["future_return"] = (df["close"].shift(-horizon) / df["close"] - 1) * 100
    df["horizon"] = horizon

    # 过滤有效样本
    if start_date is not None:
        start_dt = pd.to_datetime(start_date)
        df = df[df["date"] >= start_dt].copy()

    min_history = 60
    df = df.iloc[min_history - 1:] if len(df) >= min_history else df.iloc[0:0]

    valid_mask = df["future_return"].notna() & df["amount_share_ma5"].notna()
    df = df[valid_mask].copy()

    results = []
    for _, row in df.iterrows():
        alpha_20 = 0 if pd.isna(row["alpha_20"]) else row["alpha_20"]
        position_info = determine_position(alpha_20, row["amount_share_ma5"], sector_name=sector_name)
        momentum = determine_momentum(
            row["alpha_5"],
            0 if pd.isna(row["ma5_slope"]) else row["ma5_slope"],
            row["close"],
            row["ma5"]
        )
        behavior = determine_fund_behavior(
            amount_share_pct=row["amount_share"],
            amount_share_change=None if pd.isna(row["amount_share_change"]) else row["amount_share_change"],
            amount_share_p80=None if pd.isna(row["amount_share_p80"]) else row["amount_share_p80"],
            amount_share_high_20=None if pd.isna(row["amount_share_high_20"]) else row["amount_share_high_20"],
            bias_20=0 if pd.isna(row["bias_20"]) else row["bias_20"],
            pct=0 if pd.isna(row["pct"]) else row["pct"]
        )
        advice = determine_advice(momentum, behavior)
        is_false_kill = detect_false_kill(
            sector_data={
                "alpha_20": row["alpha_20"],
                "amount_share": row["amount_share"],
                "amount_share_p80": None if pd.isna(row["amount_share_p80"]) else row["amount_share_p80"],
            },
            market_breadth={
                "up": 0 if pd.isna(row.get("breadth_up")) else row.get("breadth_up", 0),
                "down": 0 if pd.isna(row.get("breadth_down")) else row.get("breadth_down", 0),
                "total": 0 if pd.isna(row.get("breadth_total")) else row.get("breadth_total", 0),
                "market_return": 0 if pd.isna(row.get("benchmark_pct")) else row.get("benchmark_pct", 0),
            },
            news_factor=None
        )
        signal_type = classify_signal(
            advice=advice,
            is_false_kill=is_false_kill,
            alpha_20=0 if pd.isna(row["alpha_20"]) else row["alpha_20"],
            behavior=behavior
        )

        row_result = {
            "date": row["date"].strftime("%Y-%m-%d"),
            "alpha_5": row["alpha_5"],
            "alpha_20": row["alpha_20"],
            "amount_share_ma5_pct": row["amount_share_ma5"],
            "position": position_info["位置"],
            "position_area": position_info["区域"],
            "momentum": momentum,
            "behavior": behavior,
            "advice": advice,
            "signal_type": signal_type,
            "false_kill": is_false_kill,
            "close": row["close"],
            "future_return": row["future_return"],
            "horizon": horizon
        }

        # 附加情绪数据字段（若已加载）
        for col in [
            "northbound_net_inflow",
            "margin_sse_margin_balance",
            "margin_szse_margin_balance",
            "margin_total_margin_balance",
            "breadth_up",
            "breadth_down",
            "breadth_flat",
            "breadth_total",
        ]:
            if col in row:
                val = row[col]
                row_result[col] = None if pd.isna(val) else val

        results.append(row_result)
    
    # 统计各操作建议的准确率
    advice_stats = {}
    action_stats = {
        "long": {"count": 0, "correct": 0, "returns": []},
        "avoid": {"count": 0, "correct": 0, "returns": []},
        "false_kill": {"count": 0, "correct": 0, "returns": []},
        "neutral": {"count": 0, "correct": 0, "returns": []}
    }
    for r in results:
        advice = r["advice"]
        if advice not in advice_stats:
            advice_stats[advice] = {"count": 0, "correct": 0, "returns": []}
        
        advice_stats[advice]["count"] += 1
        advice_stats[advice]["returns"].append(r["future_return"])
        
        action = r["signal_type"]
        action_stats[action]["count"] += 1
        action_stats[action]["returns"].append(r["future_return"])

        # 判断是否正确
        if "持股" in advice or "建仓" in advice or "持有" in advice:
            # 正确 = 未来涨
            if r["future_return"] > 0:
                advice_stats[advice]["correct"] += 1
        elif "离场" in advice or "止损" in advice or "回避" in advice or "观望" in advice:
            # 正确 = 未来跌
            if r["future_return"] <= 0:
                advice_stats[advice]["correct"] += 1

        if action == "long":
            if r["future_return"] > 0:
                action_stats[action]["correct"] += 1
        elif action == "avoid":
            if r["future_return"] <= 0:
                action_stats[action]["correct"] += 1
        elif action == "false_kill":
            if r["future_return"] > 0:
                action_stats[action]["correct"] += 1
    
    # 计算准确率和平均收益
    for advice in advice_stats:
        stats = advice_stats[advice]
        stats["accuracy"] = stats["correct"] / stats["count"] if stats["count"] > 0 else 0
        summary = summarize_returns(stats["returns"])
        stats.update(summary)
        stats["advice_type"] = classify_advice(advice)

    for action, stats in action_stats.items():
        stats["accuracy"] = stats["correct"] / stats["count"] if stats["count"] > 0 else 0
        stats.update(summarize_returns(stats["returns"]))
    
    return {
        "sector": sector_name,
        "thresholds": SECTOR_THRESHOLDS.get(sector_name, DEFAULT_THRESHOLDS),
        "total_samples": len(results),
        "advice_stats": advice_stats,
        "action_stats": action_stats,
        "overall_returns": summarize_returns([r["future_return"] for r in results]),
        "results": results
    }


def run_backtest_all_sectors(
    start_date: Optional[str] = None,
    horizon: int = 5,
    csv_path: Optional[str] = None,
    northbound_path: Optional[str] = "data/northbound_flow.json",
    margin_path: Optional[str] = "data/margin_balance.json",
    breadth_path: Optional[str] = "data/market_breadth.json",
    output_json: str = "data/backtest_report.json",
    summary_csv: str = "data/backtest_summary.csv",
    samples_csv: str = "data/backtest_samples.csv",
    benchmark_name: str = "科创板"
):
    """回测所有板块"""
    from fetch_sector_data import _normalize_sectors, DEFAULT_SECTORS
    
    print("=" * 60)
    print("板块生命周期系统 - 阈值回测")
    print("=" * 60)
    
    # 从 sector-daily CSV 加载数据
    import glob
    if csv_path is None:
        csv_files = glob.glob("data/sector-daily-*.csv")
        if not csv_files:
            print("错误: 未找到 sector-daily CSV 文件")
            return
        csv_path = sorted(csv_files)[-1]
    print(f"加载数据: {csv_path}")
    
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    
    # 获取指数数据
    benchmark_map = {}
    for idx_name in ["上证", "深证", "创业板", "科创板"]:
        idx_df = df[df["sector"] == idx_name].copy()
        if not idx_df.empty:
            benchmark_map[idx_name] = idx_df
    
    # 获取市场成交额
    market_amount_df = df[df["sector"].isin(["上证", "深证"])].copy()
    market_amount_df = market_amount_df.groupby("date")["amount"].sum().reset_index()
    market_amount_df.columns = ["date", "amount"]

    market_sentiment_df = load_market_sentiment_data(
        northbound_path=northbound_path,
        margin_path=margin_path,
        breadth_path=breadth_path
    )
    if market_sentiment_df.empty:
        print("提示: 未加载到情绪数据，继续执行原有回测逻辑")
    else:
        print(f"已加载情绪数据: {len(market_sentiment_df)} 条")
    
    # 获取板块列表
    sectors = _normalize_sectors(DEFAULT_SECTORS)  # 使用默认板块
    
    all_results = {}
    all_samples = []
    
    for item in sectors:
        sector_name = item["display"]
        sector_df = df[df["sector"] == sector_name].copy()
        
        if sector_df.empty:
            print(f"跳过 {sector_name}: 无数据")
            continue
        
        print(f"\n回测 {sector_name}...")
        
        # 选择基准（用科创板作为默认，后续可改为动态）
        benchmark_df = benchmark_map.get(benchmark_name, benchmark_map.get("上证"))
        if benchmark_df is None:
            print(f"  跳过 {sector_name}: 无基准数据")
            continue
        
        result = backtest_sector(
            sector_name,
            sector_df,
            benchmark_df,
            market_amount_df,
            market_sentiment_df=market_sentiment_df,
            start_date=start_date,
            horizon=horizon
        )
        all_results[sector_name] = result
        all_samples.extend(result["results"])
        
        # 打印结果
        print(f"  样本数: {result['total_samples']}")
        for advice, stats in result["advice_stats"].items():
            print(
                f"  {advice}: 准确率 {stats['accuracy']*100:.1f}%, "
                f"平均收益 {stats['avg']:+.2f}%, 中位数 {stats['median']:+.2f}%, "
                f"样本 {stats['count']}"
            )
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("汇总统计")
    print("=" * 60)
    
    advice_overall = {}
    action_overall = {
        "long": {"count": 0, "correct": 0, "returns": []},
        "avoid": {"count": 0, "correct": 0, "returns": []},
        "false_kill": {"count": 0, "correct": 0, "returns": []},
        "neutral": {"count": 0, "correct": 0, "returns": []}
    }
    for sector, result in all_results.items():
        for advice, stats in result["advice_stats"].items():
            if advice not in advice_overall:
                advice_overall[advice] = {"count": 0, "correct": 0, "returns": []}
            advice_overall[advice]["count"] += stats["count"]
            advice_overall[advice]["correct"] += stats["correct"]
            advice_overall[advice]["returns"].extend(stats.get("returns", []))

        for action, stats in result["action_stats"].items():
            action_overall[action]["count"] += stats["count"]
            action_overall[action]["correct"] += stats["correct"]
            action_overall[action]["returns"].extend(stats.get("returns", []))
    
    for advice, stats in advice_overall.items():
        accuracy = stats["correct"] / stats["count"] if stats["count"] > 0 else 0
        summary = summarize_returns(stats["returns"])
        print(
            f"{advice}: 准确率 {accuracy*100:.1f}% "
            f"({stats['correct']}/{stats['count']}), "
            f"平均收益 {summary['avg']:+.2f}%, 中位数 {summary['median']:+.2f}%"
        )

    print("\n" + "-" * 60)
    for action, stats in action_overall.items():
        stats["accuracy"] = stats["correct"] / stats["count"] if stats["count"] > 0 else 0
        summary = summarize_returns(stats["returns"])
        print(
            f"{action}：准确率 {stats['accuracy']*100:.1f}% "
            f"({stats['correct']}/{stats['count']}), "
            f"平均收益 {summary['avg']:+.2f}%, 中位数 {summary['median']:+.2f}%"
        )

    avoid_stats = action_overall["avoid"]
    false_kill_stats = action_overall["false_kill"]
    avoid_summary = summarize_returns(avoid_stats["returns"])
    false_kill_summary = summarize_returns(false_kill_stats["returns"])
    avoid_accuracy = avoid_stats["correct"] / avoid_stats["count"] if avoid_stats["count"] > 0 else 0
    false_kill_accuracy = false_kill_stats["correct"] / false_kill_stats["count"] if false_kill_stats["count"] > 0 else 0
    print("\nfalse_kill vs avoid 对比")
    print(
        f"false_kill: 样本 {false_kill_stats['count']}, 准确率 {false_kill_accuracy*100:.1f}%, "
        f"平均收益 {false_kill_summary['avg']:+.2f}%"
    )
    print(
        f"avoid: 样本 {avoid_stats['count']}, 准确率 {avoid_accuracy*100:.1f}%, "
        f"平均收益 {avoid_summary['avg']:+.2f}%"
    )
    
    overall_returns = summarize_returns([r["future_return"] for r in all_samples])
    print(
        f"\n总体收益分布：平均 {overall_returns['avg']:+.2f}% "
        f"中位数 {overall_returns['median']:+.2f}% "
        f"胜率 {overall_returns['win_rate']*100:.1f}% "
        f"样本 {overall_returns['count']}"
    )
    
    # 保存结果
    with open(output_json, "w", encoding="utf-8") as f:
        # 简化输出，只保留统计结果
        output = {
            "timestamp": datetime.now().isoformat(),
            "start_date": start_date,
            "horizon": horizon,
            "benchmark": benchmark_name,
            "total_samples": len(all_samples),
            "overall_returns": overall_returns,
            "advice_stats": {
                k: {
                    **summarize_returns(v["returns"]),
                    "count": v["count"],
                    "correct": v["correct"],
                    "accuracy": v["correct"] / v["count"] if v["count"] > 0 else 0,
                    "advice_type": classify_advice(k)
                } for k, v in advice_overall.items()
            },
            "action_stats": {
                k: {
                    **summarize_returns(v["returns"]),
                    "count": v["count"],
                    "correct": v["correct"],
                    "accuracy": v["correct"] / v["count"] if v["count"] > 0 else 0
                } for k, v in action_overall.items()
            },
            "false_kill_vs_avoid": {
                "false_kill": {
                    **false_kill_summary,
                    "count": false_kill_stats["count"],
                    "correct": false_kill_stats["correct"],
                    "accuracy": false_kill_accuracy,
                },
                "avoid": {
                    **avoid_summary,
                    "count": avoid_stats["count"],
                    "correct": avoid_stats["correct"],
                    "accuracy": avoid_accuracy,
                }
            },
            "sectors": {
                k: {
                    "thresholds": v["thresholds"],
                    "total_samples": v["total_samples"],
                    "overall_returns": v["overall_returns"],
                    "action_stats": v["action_stats"],
                    "advice_stats": v["advice_stats"]
                } for k, v in all_results.items()
            }
        }
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # 输出 CSV 报告
    if all_samples:
        samples_df = pd.DataFrame(all_samples)
        samples_df.to_csv(samples_csv, index=False, encoding="utf-8")
    
    summary_rows = []
    for sector, result in all_results.items():
        row = {
            "sector": sector,
            "samples": result["total_samples"],
            "avg_return": result["overall_returns"]["avg"],
            "median_return": result["overall_returns"]["median"],
            "win_rate": result["overall_returns"]["win_rate"]
        }
        summary_rows.append(row)
    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(summary_csv, index=False, encoding="utf-8")

    print(f"\n结果已保存到: {output_json}")
    if all_samples:
        print(f"样本明细: {samples_csv}")
    if summary_rows:
        print(f"板块汇总: {summary_csv}")
    
    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="板块生命周期系统 - 阈值回测")
    parser.add_argument("--start-date", default="2025-05-19", help="回测起始日期，例如 2024-01-01")
    parser.add_argument("--horizon", type=int, default=5, help="未来收益窗口（交易日）")
    parser.add_argument("--csv-path", default=None, help="指定 sector-daily CSV 路径")
    parser.add_argument("--northbound-path", default="data/northbound_flow.json", help="北向资金 JSON 路径")
    parser.add_argument("--margin-path", default="data/margin_balance.json", help="融资余额 JSON 路径")
    parser.add_argument("--breadth-path", default="data/market_breadth.json", help="涨跌家数 JSON 路径")
    parser.add_argument("--output-json", default="data/backtest_report.json", help="统计报告 JSON")
    parser.add_argument("--summary-csv", default="data/backtest_summary.csv", help="板块汇总 CSV")
    parser.add_argument("--samples-csv", default="data/backtest_samples.csv", help="样本明细 CSV")
    parser.add_argument("--benchmark", default="科创板", help="基准指数名称")
    args = parser.parse_args()

    run_backtest_all_sectors(
        start_date=args.start_date,
        horizon=args.horizon,
        csv_path=args.csv_path,
        northbound_path=args.northbound_path,
        margin_path=args.margin_path,
        breadth_path=args.breadth_path,
        output_json=args.output_json,
        summary_csv=args.summary_csv,
        samples_csv=args.samples_csv,
        benchmark_name=args.benchmark
    )
