#!/usr/bin/env python3
"""
阈值优化器 - 分位数阈值自动优化

功能：
1. 网格搜索最优分位数阈值
2. 对每个ETF独立优化
3. 输出最优配置到 config/thresholds/
"""
import os
import sys
import json
import argparse
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from itertools import product

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from sector_lifecycle import (
    determine_position,
    determine_position_area,
    determine_momentum,
    determine_fund_behavior,
    determine_advice,
    calculate_alpha_n_days,
    calculate_amount_share,
    calculate_amount_share_ma5,
    analyze_sector
)


def load_env():
    """加载环境变量"""
    env_path = os.path.expanduser("~/.openclaw/workspace/.env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value


load_env()


# ETF列表
ETF_LIST = [
    {"code": "sh512480", "name": "半导体"},
    {"code": "sz159852", "name": "云计算"},
    {"code": "sh516160", "name": "新能源"},
    {"code": "sh562880", "name": "商业航天"},
    {"code": "sh512010", "name": "创新药"},
    {"code": "sh512400", "name": "有色金属"},
    {"code": "sh515880", "name": "通讯设备"},
]


def load_sector_data(etf_name: str, data_dir: str = "data") -> Optional[pd.DataFrame]:
    """加载ETF日线数据（按板块名称）"""
    path = f"{data_dir}/etf_daily/etf_backfill_2026-03-09.json"

    if not os.path.exists(path):
        print(f"数据文件不存在: {path}")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 按板块名称查找数据
        sector_data = data.get(etf_name)
        if not sector_data:
            # 尝试模糊匹配
            for key in data.keys():
                if etf_name in key or key in etf_name:
                    sector_data = data[key]
                    break

        if not sector_data:
            print(f"未找到板块数据: {etf_name}")
            return None

        # 解析数据
        records = []
        for record in sector_data.get("data", []):
            date = record.get("date")
            if not date:
                continue
            try:
                records.append({
                    "date": pd.to_datetime(date),
                    "open": float(record.get("open", 0)),
                    "high": float(record.get("high", 0)),
                    "low": float(record.get("low", 0)),
                    "close": float(record.get("close", 0)),
                    "volume": float(record.get("volume", 0)),
                    "amount": float(record.get("amount", 0)),
                })
            except (ValueError, TypeError):
                continue

        if records:
            df = pd.DataFrame(records)
            df = df.sort_values("date").reset_index(drop=True)
            return df

    except Exception as e:
        print(f"加载数据失败: {e}")

    return None


def load_market_data(data_dir: str = "data") -> Optional[pd.DataFrame]:
    """加载全市场成交额数据"""
    path = f"{data_dir}/market-amount-daily.jsonl"
    if not os.path.exists(path):
        return None

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line.strip())
                date = record.get("date")
                amount = record.get("amount")
                if date and amount:
                    records.append({
                        "date": pd.to_datetime(date),
                        "amount": float(amount)
                    })
            except:
                continue

    if records:
        df = pd.DataFrame(records)
        return df.sort_values("date").reset_index(drop=True)
    return None


def calculate_metrics(
    sector_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    market_amount_df: Optional[pd.DataFrame],
    date_idx: int
) -> Optional[Dict]:
    """计算指定日期的指标（完整版）"""
    if date_idx < 60:
        return None

    sector_cut = sector_df.iloc[:date_idx + 1].copy()
    benchmark_cut = benchmark_df.iloc[:date_idx + 1].copy()

    # Alpha计算
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

    if alpha_5 is None or alpha_20 is None:
        return None

    # 资金指标
    amount_share_series = []
    if market_amount_df is not None:
        merged = pd.merge(
            sector_cut[["date", "amount"]],
            market_amount_df[["date", "amount"]],
            on="date",
            how="inner",
            suffixes=("_sector", "_market")
        )
        for _, r in merged.iterrows():
            total = r.get("amount_market", 0)
            sec = r.get("amount_sector", 0)
            if total and total > 0:
                amount_share_series.append(sec / total)

    amount_share = amount_share_series[-1] if amount_share_series else 0
    amount_share_ma5 = calculate_amount_share_ma5(amount_share_series) if amount_share_series else amount_share
    amount_share_change = amount_share / amount_share_ma5 - 1 if amount_share_ma5 else 0

    # 价格指标
    close = sector_cut["close"].iloc[-1]
    ma5 = sector_cut["close"].rolling(5).mean().iloc[-1]
    ma20 = sector_cut["close"].rolling(20).mean().iloc[-1]
    ma60 = sector_cut["close"].rolling(60).mean().iloc[-1]

    # 乖离率
    bias_20 = (close - ma20) / ma20 * 100 if ma20 and not pd.isna(ma20) else 0

    # 斜率
    ma5_series = sector_cut["close"].rolling(5).mean()
    ma60_series = sector_cut["close"].rolling(60).mean()
    ma5_slope = (ma5_series.iloc[-1] - ma5_series.iloc[-6]) / 5 if len(ma5_series) >= 6 else 0
    ma60_slope = (ma60_series.iloc[-1] - ma60_series.iloc[-6]) / 5 if len(ma60_series) >= 6 else 0

    # 当日涨跌
    pct = sector_cut["close"].pct_change().iloc[-1] * 100 if len(sector_cut) > 1 else 0

    return {
        "alpha_5": alpha_5,
        "alpha_20": alpha_20,
        "amount_share": amount_share,
        "amount_share_ma5": amount_share_ma5,
        "amount_share_change": amount_share_change,
        "bias_20": bias_20,
        "pct": pct,
        "close": close,
        "ma5": ma5 if not pd.isna(ma5) else close,
        "ma60": ma60 if not pd.isna(ma60) else close,
        "ma5_slope": ma5_slope,
        "ma60_slope": ma60_slope,
        "date": sector_cut["date"].iloc[-1]
    }


def get_future_return(sector_df: pd.DataFrame, date_idx: int, days: int = 3) -> Optional[float]:
    """计算未来N日收益"""
    if date_idx + days >= len(sector_df):
        return None

    current_price = sector_df["close"].iloc[date_idx]
    future_price = sector_df["close"].iloc[date_idx + days]

    return (future_price - current_price) / current_price


def evaluate_threshold_config(
    metrics_list: List[Dict],
    threshold_config: Dict,
    future_days: int = 3
) -> Dict:
    """
    评估某个阈值配置的效果（完整版 - 使用三层判断逻辑）

    Args:
        metrics_list: 每日指标列表
        threshold_config: 阈值配置（当前未使用，保留参数兼容性）
        future_days: 预测天数

    Returns:
        评估结果
    """
    correct = 0
    total = 0
    signals = {}
    signals_by_type = {
        "买入信号": {"correct": 0, "total": 0},
        "卖出信号": {"correct": 0, "total": 0},
        "观望信号": {"correct": 0, "total": 0}
    }

    for i, metrics in enumerate(metrics_list[:-future_days]):
        # 提取指标
        alpha_5 = metrics.get("alpha_5", 0)
        alpha_20 = metrics.get("alpha_20", 0)
        amount_share = metrics.get("amount_share", 0)
        amount_share_ma5 = metrics.get("amount_share_ma5", 0)
        amount_share_change = metrics.get("amount_share_change", 0)
        bias_20 = metrics.get("bias_20", 0)
        pct = metrics.get("pct", 0)
        close = metrics.get("close", 0)
        ma5 = metrics.get("ma5", close)
        ma5_slope = metrics.get("ma5_slope", 0)
        ma60_slope = metrics.get("ma60_slope", 0)

        # 第一层：位置判断（参考信息，不直接决定操作建议）
        # position_area = determine_position_area(alpha_20, amount_share_ma5)

        # 第二层：动能判断（使用原始值，非分位数）
        momentum = determine_momentum(alpha_5, ma5_slope, close, ma5)

        # 第三层：资金行为判断
        # 需要计算历史资金高点
        amount_share_history = [m.get("amount_share", 0) for m in metrics_list[:i+1] if m.get("amount_share")]
        amount_share_high_20 = max(amount_share_history[-20:]) if len(amount_share_history) >= 20 else (amount_share_history[-1] if amount_share_history else 0)

        behavior = determine_fund_behavior(
            amount_share_pct=amount_share,
            amount_share_change=amount_share_change,
            amount_share_p80=None,  # 简化，不计算分位数
            amount_share_high_20=amount_share_high_20,
            bias_20=bias_20,
            pct=pct
        )

        # 操作建议生成（完整映射表）
        advice = determine_advice(momentum, behavior)

        # 获取未来收益
        future_return = metrics.get("future_return")
        if future_return is None:
            continue

        # 评估准确性
        total += 1

        # 分类信号
        if advice in ["持股待涨", "积极建仓", "低吸机会", "持有"]:
            # 买入信号
            signals_by_type["买入信号"]["total"] += 1
            if future_return > 0:
                correct += 1
                signals_by_type["买入信号"]["correct"] += 1
        elif advice in ["果断离场", "果断止损", "坚决回避"]:
            # 卖出信号
            signals_by_type["卖出信号"]["total"] += 1
            if future_return < 0:
                correct += 1
                signals_by_type["卖出信号"]["correct"] += 1
        else:
            # 观望信号（持有观察、小仓埋伏等）
            signals_by_type["观望信号"]["total"] += 1
            # 观望信号不计入准确率（因为没有明确方向）

        # 统计每个建议的准确率
        signals[advice] = signals.get(advice, {"correct": 0, "total": 0})
        signals[advice]["total"] += 1

        if advice in ["持股待涨", "积极建仓", "低吸机会", "持有"]:
            if future_return > 0:
                signals[advice]["correct"] += 1
        elif advice in ["果断离场", "果断止损", "坚决回避"]:
            if future_return < 0:
                signals[advice]["correct"] += 1

    # 计算准确率（只统计有明确方向的信号）
    directional_total = signals_by_type["买入信号"]["total"] + signals_by_type["卖出信号"]["total"]
    accuracy = correct / directional_total if directional_total > 0 else 0

    return {
        "accuracy": accuracy,
        "total_signals": directional_total,
        "correct": correct,
        "signals": signals,
        "signals_by_type": signals_by_type,
        "watch_total": signals_by_type["观望信号"]["total"]
    }


def generate_threshold_combinations() -> List[Dict]:
    """生成分位数阈值组合（网格搜索）"""
    combinations = []

    # Alpha_20 的分位数阈值
    alpha_20_thresholds = [0.65, 0.70, 0.75, 0.80, 0.85]
    amount_thresholds = [0.65, 0.70, 0.75, 0.80, 0.85]
    alpha_5_thresholds = [0.60, 0.65, 0.70, 0.75, 0.80]

    for alpha_20_q in alpha_20_thresholds:
        for amount_q in amount_thresholds:
            for alpha_5_q in alpha_5_thresholds:
                config = {
                    "Alpha_20": {
                        0.8: "高位区",
                        0.6: "中高位区",
                        0.4: "中位区",
                        0.2: "低位区",
                        "default": "冰点区"
                    },
                    "Amount_Share_MA5": {
                        0.8: "高位区",
                        0.6: "中高位区",
                        0.4: "中位区",
                        0.2: "低位区",
                        "default": "冰点区"
                    },
                    "Alpha_5": {
                        0.7: "强势",
                        0.5: "偏强",
                        0.3: "偏弱",
                        "default": "弱势"
                    },
                    # 具体分位数值（用于计算）
                    "_values": {
                        "alpha_20_q80": alpha_20_q,
                        "amount_q80": amount_q,
                        "alpha_5_q70": alpha_5_q
                    }
                }
                combinations.append(config)

    return combinations


def optimize_etf_thresholds(
    etf_name: str,
    data_dir: str = "data"
) -> Optional[Dict]:
    """优化单个ETF的阈值配置"""
    print(f"\n{'='*50}")
    print(f"优化板块: {etf_name}")
    print(f"{'='*50}")

    # 加载数据
    sector_df = load_sector_data(etf_name, data_dir)
    if sector_df is None or len(sector_df) < 120:
        print(f"数据不足，跳过 {etf_name}")
        return None

    market_amount_df = load_market_data(data_dir)

    # 使用池内等权作为基准（简化）
    benchmark_df = sector_df.copy()

    # 计算每日指标
    print(f"计算指标中...")
    metrics_list = []
    for i in range(60, len(sector_df)):
        metrics = calculate_metrics(sector_df, benchmark_df, market_amount_df, i)
        if metrics is None:
            continue

        # 计算分位数（基于历史）
        historical_alpha20 = [m["alpha_20"] for m in metrics_list if m.get("alpha_20") is not None]
        historical_amount = [m["amount_share"] for m in metrics_list if m.get("amount_share") is not None]

        if len(historical_alpha20) >= 20:
            metrics["alpha_20_q"] = sum(1 for x in historical_alpha20 if x < metrics["alpha_20"]) / len(historical_alpha20)
        else:
            metrics["alpha_20_q"] = 0.5

        if len(historical_amount) >= 20:
            metrics["amount_share_q"] = sum(1 for x in historical_amount if x < metrics["amount_share"]) / len(historical_amount)
        else:
            metrics["amount_share_q"] = 0.5

        # Alpha_5 分位数
        historical_alpha5 = [m["alpha_5"] for m in metrics_list if m.get("alpha_5") is not None]
        if len(historical_alpha5) >= 20:
            metrics["alpha_5_q"] = sum(1 for x in historical_alpha5 if x < metrics["alpha_5"]) / len(historical_alpha5)
        else:
            metrics["alpha_5_q"] = 0.5

        # 资金变化分位数
        historical_change = [m["amount_share_change"] for m in metrics_list if m.get("amount_share_change") is not None]
        if len(historical_change) >= 20:
            metrics["amount_change_q"] = sum(1 for x in historical_change if x < metrics["amount_share_change"]) / len(historical_change)
        else:
            metrics["amount_change_q"] = 0.5

        # 未来收益
        metrics["future_return"] = get_future_return(sector_df, i, days=3)

        metrics_list.append(metrics)

    print(f"有效数据点: {len(metrics_list)}")

    if len(metrics_list) < 50:
        print(f"数据点不足，跳过")
        return None

    # 网格搜索最优阈值
    print(f"网格搜索中（{len(generate_threshold_combinations())} 种组合）...")
    best_config = None
    best_accuracy = 0
    best_eval = None

    for j, config in enumerate(generate_threshold_combinations()):
        if j % 25 == 0:
            print(f"  进度: {j}/{len(generate_threshold_combinations())}")

        result = evaluate_threshold_config(metrics_list, config)

        if result["total_signals"] >= 10 and result["accuracy"] > best_accuracy:
            best_accuracy = result["accuracy"]
            best_config = config.copy()
            best_eval = result

    if best_config:
        # 清理结果
        if "_evaluation" in best_config:
            del best_config["_evaluation"]

        print(f"最优准确率: {best_accuracy:.2%} (信号数: {best_eval['total_signals']})")
        print(f"最优配置: {best_config.get('_values')}")

        return {
            "etf_name": etf_name,
            "accuracy": best_accuracy,
            "config": best_config,
            "data_points": len(metrics_list)
        }
    else:
        print("未找到满足条件的阈值配置")
        # 返回默认配置
        return {
            "etf_name": etf_name,
            "accuracy": 0,
            "config": generate_threshold_combinations()[0],
            "data_points": len(metrics_list)
        }


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="阈值优化器")
    parser.add_argument("--etf", type=str, help="指定板块名称（如：半导体）")
    parser.add_argument("--output", type=str, default="config/thresholds", help="输出目录")
    args = parser.parse_args()

    # 确保输出目录存在
    os.makedirs(args.output, exist_ok=True)

    # 选择要优化的ETF
    if args.etf:
        etf_list = [e for e in ETF_LIST if args.etf in e["name"] or e["name"] in args.etf]
    else:
        etf_list = ETF_LIST

    results = []

    for etf in etf_list:
        result = optimize_etf_thresholds(etf["name"])
        if result:
            results.append(result)

            # 保存结果
            output_file = os.path.join(args.output, f"{result['etf_name']}.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result["config"], f, ensure_ascii=False, indent=2)
            print(f"已保存: {output_file}")

    # 保存汇总报告
    summary_file = os.path.join(args.output, "summary.json")
    summary = {
        "optimize_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results
    }
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"优化完成！结果已保存到 {args.output}/")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
