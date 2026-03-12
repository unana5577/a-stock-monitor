#!/usr/bin/env python3
"""测试不同分位数下的放量启动信号"""
import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_sector_data(etf_name: str):
    """加载ETF数据"""
    path = "data/etf_daily/etf_backfill_2026-03-09.json"
    with open(path, "r") as f:
        data = json.load(f)

    sector_data = data.get(etf_name)
    records = []
    for record in sector_data.get("data", []):
        records.append({
            "date": pd.to_datetime(record.get("date")),
            "close": float(record.get("close", 0)),
            "amount": float(record.get("amount", 0)),
        })

    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def main():
    df = load_sector_data("半导体")

    # 只使用2026年的数据（最近60个交易日）
    df_2026 = df[df['date'].dt.year == 2026].reset_index(drop=True)

    if len(df_2026) < 40:
        print("2026年数据不足，需要至少40天数据")
        return

    # 使用2026年之前的数据作为训练集
    history_df = df[df['date'].dt.year < 2026]
    test_df = df_2026

    print(f"=" * 100)
    print(f"半导体ETF：放量启动信号测试（2026年数据，共{len(test_df)}个交易日）")
    print(f"训练数据：{history_df['date'].iloc[0].date()} 到 {history_df['date'].iloc[-1].date()} ({len(history_df)}天)")
    print(f"测试数据：{test_df['date'].iloc[0].date()} 到 {test_df['date'].iloc[-1].date()} ({len(test_df)}天)")
    print(f"=" * 100)

    # 计算历史 Amount_Share_Change
    amount_share_series = history_df["amount"].tolist()
    historical_changes = []
    for i in range(5, len(amount_share_series)):
        ma5 = np.mean(amount_share_series[max(0, i-5):i+1])
        if ma5 > 0:
            change = amount_share_series[i] / ma5 - 1
            historical_changes.append(change)

    # 计算不同分位数
    quantiles = {
        "50%分位": 0.5,
        "60%分位": 0.6,
        "70%分位": 0.7,
        "80%分位": 0.8,
        "90%分位": 0.9,
    }

    print(f"\n【历史Amount_Share_Change分布】（用于训练）")
    print(f"样本数: {len(historical_changes)}")
    print(f"最小值: {min(historical_changes)*100:.2f}%")
    print(f"最大值: {max(historical_changes)*100:.2f}%")
    print(f"平均值: {np.mean(historical_changes)*100:.2f}%")
    print(f"\n不同分位数阈值：")
    for q_name, q_val in quantiles.items():
        threshold = np.percentile(historical_changes, q_val * 100)
        print(f"  {q_name}: {threshold*100:.2f}%")

    # 测试最后60天
    print(f"\n{'='*100}")
    print(f"【测试结果】最近60天中被识别为'放量启动'的日期")
    print(f"{'='*100}\n")

    for q_name, q_val in quantiles.items():
        threshold = np.percentile(historical_changes, q_val * 100)

        # 找出所有超过阈值的日期
        volume_start_dates = []
        for i in range(len(test_df)):
            # 计算当天的 Amount_Share_Change
            if i < 5:
                continue

            current_amount = test_df["amount"].iloc[i]
            ma5 = np.mean(test_df["amount"].iloc[max(0, i-5):i+1])
            change = current_amount / ma5 - 1

            pct = test_df["close"].pct_change().iloc[i] * 100

            # 判断是否放量启动
            if change > threshold and pct > 0:
                volume_start_dates.append({
                    "date": test_df["date"].iloc[i].date(),
                    "close": test_df["close"].iloc[i],
                    "amount": current_amount,
                    "change_pct": change * 100,
                    "pct": pct,
                    "amount_ma5": ma5
                })

        print(f"\n【{q_name}】阈值: {threshold*100:.2f}%  |  识别出 {len(volume_start_dates)} 个放量启动日")
        print(f"{'-'*100}")

        if len(volume_start_dates) == 0:
            print("  （无信号）")
        else:
            print(f"{'日期':<12} {'收盘价':<8} {'成交额(亿)':<12} {'变化率':<10} {'涨幅':<8} {'成交MA5':<12}")
            for d in volume_start_dates:
                print(f"{str(d['date']):<12} {d['close']:<8.2f} {d['amount']/1e8:<12.2f} {d['change_pct']:<10.2f}% {d['pct']:<8.2f}% {d['amount_ma5']/1e8:<12.2f}")

    print(f"\n{'='*100}")
    print(f"【验证建议】")
    print(f"1. 查看90%分位：只识别最极端的放量（应该很少，但最明显）")
    print(f"2. 查看80%分位：文档定义的标准（平衡准确性和信号数量）")
    print(f"3. 查看60-70%分位：更敏感，可能捕捉到早期启动信号")
    print(f"4. 对比实际K线图：验证这些日期是否真的有明显的资金进场")
    print(f"{'='*100}")


if __name__ == "__main__":
    main()
