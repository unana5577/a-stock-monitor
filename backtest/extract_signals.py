#!/usr/bin/env python3
"""提取MA3和MA5判断的所有信号日期"""
import os
import sys
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def recognize_kline(open_price, close_price, high_price, low_price):
    body = abs(close_price - open_price)
    if open_price == 0:
        return "普通K线"
    body_pct = body / open_price * 100
    if body_pct < 1.0:
        upper_shadow = high_price - max(open_price, close_price)
        lower_shadow = min(open_price, close_price) - low_price
        total_range = high_price - low_price
        if total_range > 0 and lower_shadow > upper_shadow * 2 and lower_shadow > body * 0.5:
            return "锤子线"
        if total_range > 0 and upper_shadow > lower_shadow * 2 and upper_shadow > body * 0.5:
            return "射击之星"
        return "十字星"
    if body_pct > 3.0 and close_price > open_price:
        return "大阳线"
    if body_pct > 3.0 and close_price < open_price:
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

    # 收集所有信号
    ma3_signals = []
    ma5_signals = []

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

        if behavior_ma3 != "横盘整理":
            ma3_signals.append({
                "date": row['date'].date(),
                "close": row['close'],
                "pct": pct,
                "vol_ratio": vol_ratio_ma3,
                "bias": bias_20,
                "kline": kline_type,
                "behavior": behavior_ma3
            })
        if behavior_ma5 != "横盘整理":
            ma5_signals.append({
                "date": row['date'].date(),
                "close": row['close'],
                "pct": pct,
                "vol_ratio": vol_ratio_ma5,
                "bias": bias_20,
                "kline": kline_type,
                "behavior": behavior_ma5
            })

    print("=" * 80)
    print("【MA3 有信号的日期】（共{}个）".format(len(ma3_signals)))
    print("=" * 80)
    print(f"{'日期':<12} {'收盘':<6} {'涨幅':<8} {'量比':<8} {'BIAS':<8} {'K线':<8} {'判断':<12}")
    print("-" * 80)
    for s in ma3_signals:
        print(f"{str(s['date']):<12} {s['close']:<6.2f} {s['pct']:>6.2f}% {s['vol_ratio']:>6.2f}x {s['bias']:>6.1f}% {s['kline']:<8} {s['behavior']:<12}")

    print("\n" + "=" * 80)
    print("【MA5 有信号的日期】（共{}个）".format(len(ma5_signals)))
    print("=" * 80)
    print(f"{'日期':<12} {'收盘':<6} {'涨幅':<8} {'量比':<8} {'BIAS':<8} {'K线':<8} {'判断':<12}")
    print("-" * 80)
    for s in ma5_signals:
        print(f"{str(s['date']):<12} {s['close']:<6.2f} {s['pct']:>6.2f}% {s['vol_ratio']:>6.2f}x {s['bias']:>6.1f}% {s['kline']:<8} {s['behavior']:<12}")


if __name__ == "__main__":
    main()
