#!/usr/bin/env python3
"""分析MA3和MA5判断不一致的日期"""
import os
import sys
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def recognize_kline(open_price, close_price, high_price, low_price):
    body = abs(close_price - open_price)
    total_range = high_price - low_price
    if total_range == 0:
        return "普通K线"
    body_ratio = body / total_range
    if body_ratio < 0.15:
        upper_shadow = high_price - max(open_price, close_price)
        lower_shadow = min(open_price, close_price) - low_price
        if lower_shadow > upper_shadow * 2 and lower_shadow > body:
            return "锤子线"
        if upper_shadow > lower_shadow * 2 and upper_shadow > body:
            return "射击之星"
        return "十字星"
    if body_ratio > 0.6 and close_price > open_price:
        return "大阳线"
    if body_ratio > 0.6 and close_price < open_price:
        return "大阴线"
    if close_price > open_price:
        return "小阳线"
    else:
        return "小阴线"


def determine_fund_behavior_new(amount, amount_ma, pct, bias_20, kline_type, use_ma3=True):
    volume_ratio = amount / amount_ma if amount_ma > 0 else 0

    if pct > 0 and volume_ratio > 1.3:
        return "放量启动"
    if pct < 0 and volume_ratio > 1.3:
        return "恐慌出逃"
    if volume_ratio < 0.7 and bias_20 < -8 and kline_type in ["锤子线", "十字星", "小阳线"]:
        return "超跌反弹"
    if volume_ratio < 0.7 and kline_type == "十字星":
        return "观望"
    if bias_20 > 8 and kline_type in ["射击之星", "大阴线"]:
        return "加速赶顶"
    if bias_20 > 8 and volume_ratio > 1.3:
        return "加速赶顶"
    if volume_ratio < 0.8 and bias_20 > 5:
        return "资金撤退"
    return "横盘整理"


def load_sector_data(etf_name):
    path = "data/etf_daily/etf_backfill_2026-03-09.json"
    with open(path, "r") as f:
        data = json.load(f)
    sector_data = data.get(etf_name)
    records = []
    for record in sector_data.get("data", []):
        records.append({
            "date": pd.to_datetime(record.get("date")),
            "open": float(record.get("open", 0)),
            "close": float(record.get("close", 0)),
            "high": float(record.get("high", 0)),
            "low": float(record.get("low", 0)),
            "amount": float(record.get("amount", 0)),
        })
    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def main():
    df = load_sector_data("半导体")
    df_test = df[df['date'] >= '2025-07-01'].reset_index(drop=True)

    df_test['amount_ma3'] = df_test['amount'].rolling(3).mean()
    df_test['amount_ma5'] = df_test['amount'].rolling(5).mean()
    df_test['ma20'] = df_test['close'].rolling(20).mean()
    df_test['bias_20'] = (df_test['close'] - df_test['ma20']) / df_test['ma20'] * 100
    df_test['kline'] = df_test.apply(lambda r: recognize_kline(r['open'], r['close'], r['high'], r['low']), axis=1)
    df_test['pct'] = df_test['close'].pct_change() * 100

    print("=" * 100)
    print("【MA3 vs MA5 判断不一致的日期分析】")
    print("=" * 100)
    print(f"\n{'日期':<12} {'收盘':<6} {'涨幅':<8} {'量比MA3':<10} {'量比MA5':<10} {'BIAS':<8} {'K线':<8} {'MA3':<12} {'MA5':<12} {'差异'}")
    print("-" * 110)

    diff_ma3_only = []  # MA3有信号，MA5没有
    diff_ma5_only = []  # MA5有信号，MA3没有
    both_signal = []     # 两者都有

    for i in range(25, len(df_test)):
        row = df_test.iloc[i]
        pct = row['pct'] if pd.notna(row['pct']) else 0
        bias_20 = row['bias_20'] if pd.notna(row['bias_20']) else 0
        kline_type = row['kline']
        amount = row['amount']
        amount_ma3 = row['amount_ma3'] if pd.notna(row['amount_ma3']) else amount
        amount_ma5 = row['amount_ma5'] if pd.notna(row['amount_ma5']) else amount

        vol_ratio_ma3 = amount / amount_ma3 if amount_ma3 > 0 else 0
        vol_ratio_ma5 = amount / amount_ma5 if amount_ma5 > 0 else 0

        behavior_ma3 = determine_fund_behavior_new(amount, amount_ma3, pct, bias_20, kline_type, True)
        behavior_ma5 = determine_fund_behavior_new(amount, amount_ma5, pct, bias_20, kline_type, False)

        is_signal_ma3 = behavior_ma3 != "横盘整理"
        is_signal_ma5 = behavior_ma5 != "横盘整理"

        if is_signal_ma3 != is_signal_ma5:
            if is_signal_ma3 and not is_signal_ma5:
                diff_ma3_only.append((row, behavior_ma3, vol_ratio_ma3, vol_ratio_ma5))
            elif is_signal_ma5 and not is_signal_ma3:
                diff_ma5_only.append((row, behavior_ma5, vol_ratio_ma3, vol_ratio_ma5))
        elif is_signal_ma3 and is_signal_ma5:
            both_signal.append((row, behavior_ma3, behavior_ma5, vol_ratio_ma3, vol_ratio_ma5))

    # 打印MA3独有信号
    print("\n【A. MA3独有信号（MA5未识别）】")
    if diff_ma3_only:
        for row, behavior, vr_ma3, vr_ma5 in diff_ma3_only:
            print(f"{str(row['date'].date()):<12} {row['close']:<6.2f} {row['pct']:>6.2f}% {vr_ma3:>8.2f}x {vr_ma5:>8.2f}x {row['bias_20']:>6.1f}% {row['kline']:<8} {behavior:<12} {'-':<12} {'⭐MA3':<8}")
    else:
        print("  （无）")

    # 打印MA5独有信号
    print("\n【B. MA5独有信号（MA3未识别）】")
    if diff_ma5_only:
        for row, behavior, vr_ma3, vr_ma5 in diff_ma5_only:
            print(f"{str(row['date'].date()):<12} {row['close']:<6.2f} {row['pct']:>6.2f}% {vr_ma3:>8.2f}x {vr_ma5:>8.2f}x {row['bias_20']:>6.1f}% {row['kline']:<8} {'-':<12} {behavior:<12} {'⭐MA5':<8}")
    else:
        print("  （无）")

    print(f"\n【统计】")
    print(f"  MA3独有: {len(diff_ma3_only)} 次")
    print(f"  MA5独有: {len(diff_ma5_only)} 次")
    print(f"  两者都有: {len(both_signal)} 次")

    print(f"\n【结论】")
    print(f"  MA5比MA3多识别 {len(diff_ma5_only) - len(diff_ma3_only)} 个信号")
    print(f"  原因分析：MA5更平滑，量比变化更稳定，更容易触发阈值")


if __name__ == "__main__":
    main()
