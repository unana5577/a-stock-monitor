# -*- coding: utf-8 -*-
"""
回测脚本
验证板块生命周期判断逻辑的准确性
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json

from sector_lifecycle import analyze_sector
from sector_lifecycle_config import SECTORS, BACKTEST_CONFIG
from fetch_sector_data import fetch_all_sectors, fetch_index_hist


# ============================================
# 回测配置
# ============================================

VALIDATION_DAYS = BACKTEST_CONFIG["validation_days"]  # 验证未来 N 日涨跌
START_DATE = BACKTEST_CONFIG["start_date"]


# ============================================
# 回测逻辑
# ============================================

def validate_prediction(
    advice: str,
    future_return: float
) -> bool:
    """
    验证预测是否正确
    
    Args:
        advice: 操作建议
        future_return: 未来 N 日收益率（百分比，如 5.0 表示 5%）
    
    Returns:
        是否正确
    """
    # 做多类建议：未来应该上涨
    long_keywords = ["持有", "建仓", "低吸", "埋伏", "待涨"]
    
    # 做空/观望类建议：未来应该下跌或横盘
    short_keywords = ["离场", "止损", "清仓", "减仓", "观望", "空仓"]
    
    # 判断建议类型
    is_long = any(keyword in advice for keyword in long_keywords)
    is_short = any(keyword in advice for keyword in short_keywords)
    
    # 验证逻辑
    if is_long and not is_short:
        # 做多建议：未来应该上涨
        return future_return > 0
    elif is_short and not is_long:
        # 做空/观望建议：未来应该下跌
        return future_return < 0
    else:
        # 无法判断的建议（如"观望"、"待观察"）
        # 使用绝对值判断：预测方向正确即可
        if "观望" in advice or "观察" in advice:
            # 观望建议：横盘或小幅波动
            return abs(future_return) < 3.0
        else:
            # 其他情况：默认认为正确
            return True


def backtest_sector(
    sector_df: pd.DataFrame,
    market_df: pd.DataFrame,
    sector_name: str,
    validation_days: int = 5
) -> List[Dict]:
    """
    回测单个板块
    
    Args:
        sector_df: 板块历史数据
        market_df: 市场历史数据
        sector_name: 板块名称
        validation_days: 验证未来 N 日
    
    Returns:
        回测结果列表
    """
    results = []
    
    # 确保数据足够长
    if len(sector_df) < 30 or len(market_df) < 30:
        print(f"⚠️  {sector_name} 数据不足，跳过")
        return results
    
    # 遍历每个交易日（从第 20 天开始，留出前 20 天计算指标）
    for i in range(20, len(sector_df) - validation_days):
        # 截取到当前日期的数据
        current_sector = sector_df.iloc[:i+1]
        current_market = market_df.iloc[:i+1]
        
        # 分析板块生命周期
        analysis = analyze_sector(current_sector, current_market, sector_name)
        
        # 获取未来 N 日收益
        future_sector = sector_df.iloc[i+1:i+1+validation_days]
        if len(future_sector) < validation_days:
            continue
        
        # 计算累计收益
        future_return = (1 + future_sector["pct"] / 100).prod() - 1
        future_return_pct = future_return * 100
        
        # 验证预测
        is_correct = validate_prediction(analysis["advice"], future_return_pct)
        
        # 记录结果
        results.append({
            "date": sector_df.iloc[i]["date"],
            "sector": sector_name,
            "position_zone": analysis["position_zone"],
            "position_name": analysis["position_name"],
            "stage_signal": analysis["stage_signal"],
            "display_name": analysis["display_name"],
            "advice": analysis["advice"],
            "alpha_20": analysis["alpha_20"],
            "amount_share": analysis["amount_share"],
            "future_return": round(future_return_pct, 2),
            "is_correct": is_correct
        })
    
    return results


def backtest_all_sectors(
    start_date: str = START_DATE,
    validation_days: int = VALIDATION_DAYS
) -> List[Dict]:
    """
    回测所有板块
    
    Args:
        start_date: 起始日期
        validation_days: 验证未来 N 日
    
    Returns:
        所有板块的回测结果
    """
    print("=" * 60)
    print("开始回测")
    print("=" * 60)
    print(f"起始日期: {start_date}")
    print(f"验证天数: {validation_days} 日")
    print("=" * 60)
    
    # 1. 获取数据
    print("\n📥 获取数据...")
    sector_data = fetch_all_sectors(start_date)
    
    # 获取上证指数作为市场基准
    market_df = fetch_index_hist("000001.SH", start_date)
    
    if market_df.empty:
        print("❌ 无法获取市场数据")
        return []
    
    # 2. 逐个板块回测
    all_results = []
    
    for sector_name, sector_df in sector_data.items():
        print(f"\n📊 回测 {sector_name}...")
        results = backtest_sector(sector_df, market_df, sector_name, validation_days)
        all_results.extend(results)
        print(f"  样本数: {len(results)}")
    
    print(f"\n总计样本数: {len(all_results)}")
    
    return all_results


# ============================================
# 统计分析
# ============================================

def calculate_metrics(results: List[Dict]) -> Dict:
    """
    计算统计指标
    
    Args:
        results: 回测结果列表
    
    Returns:
        统计指标字典
    """
    if not results:
        return {}
    
    df = pd.DataFrame(results)
    
    # 1. 总体准确率
    total_samples = len(df)
    correct_samples = df["is_correct"].sum()
    overall_accuracy = correct_samples / total_samples if total_samples > 0 else 0
    
    # 2. 各操作建议准确率
    advice_accuracy = df.groupby("advice").agg({
        "is_correct": ["sum", "count"],
        "future_return": "mean"
    }).round(2)
    
    advice_accuracy.columns = ["correct", "total", "avg_return"]
    advice_accuracy["accuracy"] = (advice_accuracy["correct"] / advice_accuracy["total"] * 100).round(1)
    advice_accuracy = advice_accuracy.sort_values("total", ascending=False)
    
    # 3. 各板块准确率
    sector_accuracy = df.groupby("sector").agg({
        "is_correct": ["sum", "count"],
        "future_return": "mean"
    }).round(2)
    
    sector_accuracy.columns = ["correct", "total", "avg_return"]
    sector_accuracy["accuracy"] = (sector_accuracy["correct"] / sector_accuracy["total"] * 100).round(1)
    
    # 4. 胜率（正收益比例）
    win_rate = (df["future_return"] > 0).sum() / total_samples if total_samples > 0 else 0
    
    # 5. 平均收益
    avg_return = df["future_return"].mean()
    
    # 6. 夏普比率（简化版）
    sharpe_ratio = df["future_return"].mean() / df["future_return"].std() if df["future_return"].std() != 0 else 0
    
    # 7. 最大回撤
    cumulative_return = (1 + df["future_return"] / 100).cumprod()
    max_drawdown = (cumulative_return / cumulative_return.cummax() - 1).min()
    
    return {
        "total_samples": total_samples,
        "correct_samples": int(correct_samples),
        "overall_accuracy": round(overall_accuracy * 100, 1),
        "win_rate": round(win_rate * 100, 1),
        "avg_return": round(avg_return, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "advice_accuracy": advice_accuracy.to_dict("index"),
        "sector_accuracy": sector_accuracy.to_dict("index")
    }


def print_report(metrics: Dict):
    """
    打印回测报告
    
    Args:
        metrics: 统计指标字典
    """
    print("\n" + "=" * 60)
    print("回测报告")
    print("=" * 60)
    
    print(f"\n📊 总体指标:")
    print(f"  样本数: {metrics['total_samples']}")
    print(f"  正确数: {metrics['correct_samples']}")
    print(f"  准确率: {metrics['overall_accuracy']}%")
    print(f"  胜率: {metrics['win_rate']}%")
    print(f"  平均收益: {metrics['avg_return']}%")
    print(f"  夏普比率: {metrics['sharpe_ratio']}")
    print(f"  最大回撤: {metrics['max_drawdown']}%")
    
    print(f"\n📈 各操作建议准确率:")
    for advice, stats in sorted(metrics['advice_accuracy'].items(), key=lambda x: x[1]['total'], reverse=True):
        print(f"  {advice:15} | 样本: {int(stats['total']):4} | 准确率: {stats['accuracy']:5.1f}% | 平均收益: {stats['avg_return']:6.2f}%")
    
    print(f"\n📊 各板块准确率:")
    for sector, stats in sorted(metrics['sector_accuracy'].items(), key=lambda x: x[1]['accuracy'], reverse=True):
        print(f"  {sector:10} | 样本: {int(stats['total']):4} | 准确率: {stats['accuracy']:5.1f}% | 平均收益: {stats['avg_return']:6.2f}%")
    
    print("\n" + "=" * 60)


def save_report(metrics: Dict, filename: str = "backtest_report.json"):
    """
    保存回测报告
    
    Args:
        metrics: 统计指标字典
        filename: 文件名
    """
    import os
    
    save_dir = os.path.expanduser("~/股票项目/data/reports")
    os.makedirs(save_dir, exist_ok=True)
    
    filepath = os.path.join(save_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    
    print(f"💾 报告已保存: {filepath}")


# ============================================
# 主函数
# ============================================

def main():
    """主函数"""
    # 1. 运行回测
    results = backtest_all_sectors(START_DATE, VALIDATION_DAYS)
    
    if not results:
        print("❌ 回测失败，无有效数据")
        return
    
    # 2. 计算统计指标
    metrics = calculate_metrics(results)
    
    # 3. 打印报告
    print_report(metrics)
    
    # 4. 保存报告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_report(metrics, f"backtest_report_{timestamp}.json")
    
    # 5. 保存详细结果
    df = pd.DataFrame(results)
    save_path = os.path.expanduser(f"~/股票项目/data/reports/backtest_details_{timestamp}.csv")
    df.to_csv(save_path, index=False, encoding="utf-8")
    print(f"💾 详细结果已保存: {save_path}")


if __name__ == "__main__":
    import os
    main()
