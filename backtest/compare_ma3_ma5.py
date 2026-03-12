#!/usr/bin/env python3
"""对比3日均量和5日均量的资金行为判断"""
import os
import sys
import json
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def recognize_kline(open_price, close_price, high_price, low_price):
    """识别K线形态

    十字星定义：收盘价与开盘价差异 < 1%
    - 上升趋势中出现：可能预示向下转折
    - 下降趋势中出现：可能预示止跌
    """
    body = abs(close_price - open_price)
    if open_price == 0:
        return "普通K线"

    # 涨跌幅百分比
    body_pct = body / open_price * 100

    # 十字星：涨跌幅 < 1%
    if body_pct < 1.0:
        # 判断上下影线
        upper_shadow = high_price - max(open_price, close_price)
        lower_shadow = min(open_price, close_price) - low_price
        total_range = high_price - low_price

        if total_range > 0 and lower_shadow > upper_shadow * 2 and lower_shadow > body * 0.5:
            return "锤子线"  # 底部长下影（可能止跌）
        if total_range > 0 and upper_shadow > lower_shadow * 2 and upper_shadow > body * 0.5:
            return "射击之星"  # 顶部上影线（可能见顶）
        return "十字星"

    # 大阳线：涨幅 > 3%
    if body_pct > 3.0 and close_price > open_price:
        return "大阳线"

    # 大阴线：跌幅 > 3%
    if body_pct > 3.0 and close_price < open_price:
        return "大阴线"

    # 小阳线
    if close_price > open_price:
        return "小阳线"
    else:
        return "小阴线"


def determine_fund_behavior_new(
    amount: float,
    amount_ma: float,
    pct: float,
    bias_20: float,
    kline_type: str,
    amount_ma3: float = None,
    amount_ma5: float = None,
    use_ma3: bool = True
) -> str:
    """新的资金行为判断（多指标交叉验证）"""

    # 选择用3日还是5日均量
    if use_ma3 and amount_ma3:
        ref_ma = amount_ma3
    else:
        ref_ma = amount_ma

    if ref_ma == 0:
        return "横盘整理"

    volume_ratio = amount / ref_ma

    # === 优先级1：明显的放量信号（当日确认）===

    # 放量启动：放量30%以上 + 上涨
    if pct > 0 and volume_ratio > 1.3:
        return "放量启动"

    # 放量下跌：放量30%以上 + 下跌
    if pct < 0 and volume_ratio > 1.3:
        return "恐慌出逃"

    # === 优先级2：冰点信号（缩量+超跌+K线确认）===

    if volume_ratio < 0.7:  # 缩量30%以上
        if bias_20 < -8:  # 超跌
            if kline_type in ["锤子线", "十字星", "小阳线"]:
                return "超跌反弹"
        elif kline_type == "十字星":
            return "观望"  # 止跌信号，但方向未明
        return "横盘整理"

    # === 优先级3：到顶信号 ===

    if bias_20 > 8:  # 超涨
        if kline_type in ["射击之星", "大阴线"]:
            return "加速赶顶"
        if volume_ratio > 1.3:  # 放量滞涨
            return "加速赶顶"

    # === 优先级4：资金撤退（从高位回落）===

    if volume_ratio < 0.8:  # 缩量
        if bias_20 > 5:  # 之前在高位
            return "资金撤退"

    # === 默认 ===
    return "横盘整理"


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
            "open": float(record.get("open", 0)),
            "close": float(record.get("close", 0)),
            "high": float(record.get("high", 0)),
            "low": float(record.get("low", 0)),
            "amount": float(record.get("amount", 0)),
        })

    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


def main():
    df = load_sector_data("半导体")

    # 使用2025年下半年+2026年的数据（有足够训练数据）
    df_2026 = df[df['date'] >= '2025-07-01'].reset_index(drop=True)

    if len(df_2026) < 20:
        print("2026年数据不足")
        return

    print(f"=" * 90)
    print(f"半导体ETF：3日均量 vs 5日均量 对比（{df_2026['date'].iloc[0].date()} 到 {df_2026['date'].iloc[-1].date()}，共{len(df_2026)}天）")
    print(f"=" * 90)

    # 计算3日和5日均量
    df_2026['amount_ma3'] = df_2026['amount'].rolling(3).mean()
    df_2026['amount_ma5'] = df_2026['amount'].rolling(5).mean()

    # 计算乖离率
    df_2026['ma20'] = df_2026['close'].rolling(20).mean()
    df_2026['bias_20'] = (df_2026['close'] - df_2026['ma20']) / df_2026['ma20'] * 100

    # 识别K线
    df_2026['kline'] = df_2026.apply(
        lambda r: recognize_kline(r['open'], r['close'], r['high'], r['low']),
        axis=1
    )

    # 计算涨跌幅
    df_2026['pct'] = df_2026['close'].pct_change() * 100

    # 统计结果
    results_ma3 = {"放量启动": 0, "恐慌出逃": 0, "超跌反弹": 0, "加速赶顶": 0, "资金撤退": 0, "横盘整理": 0, "观望": 0}
    results_ma5 = {"放量启动": 0, "恐慌出逃": 0, "超跌反弹": 0, "加速赶顶": 0, "资金撤退": 0, "横盘整理": 0, "观望": 0}

    print(f"\n{'日期':<12} {'收盘':<6} {'涨幅':<8} {'量比MA3':<10} {'量比MA5':<10} {'K线':<8} {'BIAS':<8} {'MA3判断':<12} {'MA5判断':<12}")
    print("-" * 115)

    for i in range(25, len(df_2026)):  # 从第25天开始（有足够的历史数据计算MA5/MA3/MA20）
        row = df_2026.iloc[i]

        pct = row['pct'] if pd.notna(row['pct']) else 0
        bias_20 = row['bias_20'] if pd.notna(row['bias_20']) else 0
        kline_type = row['kline']
        amount = row['amount']
        amount_ma3 = row['amount_ma3'] if pd.notna(row['amount_ma3']) else amount
        amount_ma5 = row['amount_ma5'] if pd.notna(row['amount_ma5']) else amount

        # MA3判断
        behavior_ma3 = determine_fund_behavior_new(
            amount=amount,
            amount_ma=amount_ma3,
            pct=pct,
            bias_20=bias_20,
            kline_type=kline_type,
            amount_ma3=amount_ma3,
            amount_ma5=amount_ma5,
            use_ma3=True
        )
        results_ma3[behavior_ma3] = results_ma3.get(behavior_ma3, 0) + 1

        # MA5判断
        behavior_ma5 = determine_fund_behavior_new(
            amount=amount,
            amount_ma=amount_ma5,
            pct=pct,
            bias_20=bias_20,
            kline_type=kline_type,
            amount_ma3=amount_ma3,
            amount_ma5=amount_ma5,
            use_ma3=False
        )
        results_ma5[behavior_ma5] = results_ma5.get(behavior_ma5, 0) + 1

        # 打印每一天的详细数据
        vol_ratio_ma3 = amount / amount_ma3 if amount_ma3 > 0 else 0
        vol_ratio_ma5 = amount / amount_ma5 if amount_ma5 > 0 else 0
        print(f"{str(row['date'].date()):<12} {row['close']:<6.2f} {pct:>6.2f}% {vol_ratio_ma3:>8.2f}x {vol_ratio_ma5:>8.2f}x {kline_type:<8} {bias_20:>6.1f}% {behavior_ma3:<12} {behavior_ma5:<12}")

    print("\n" + "=" * 90)
    print("【统计汇总】")
    print("=" * 90)

    print(f"\n{'指标':<12} {'放量启动':<10} {'恐慌出逃':<10} {'超跌反弹':<10} {'加速赶顶':<10} {'资金撤退':<10} {'横盘整理':<10} {'观望':<10}")
    print("-" * 90)

    ma3_total = sum(results_ma3.values())
    ma5_total = sum(results_ma5.values())

    print(f"{'MA3':<12} {results_ma3['放量启动']:<10} {results_ma3['恐慌出逃']:<10} {results_ma3['超跌反弹']:<10} {results_ma3['加速赶顶']:<10} {results_ma3['资金撤退']:<10} {results_ma3['横盘整理']:<10} {results_ma3['观望']:<10}")
    print(f"{'MA5':<12} {results_ma5['放量启动']:<10} {results_ma5['恐慌出逃']:<10} {results_ma5['超跌反弹']:<10} {results_ma5['加速赶顶']:<10} {results_ma5['资金撤退']:<10} {results_ma5['横盘整理']:<10} {results_ma5['观望']:<10}")

    # 计算有效信号率
    ma3_signal_count = ma3_total - results_ma3['横盘整理']
    ma5_signal_count = ma5_total - results_ma5['横盘整理']

    print(f"\n【关键对比】")
    print(f"3日均量有效信号: {ma3_signal_count} ({ma3_signal_count/ma3_total*100:.1f}%)")
    print(f"5日均量有效信号: {ma5_signal_count} ({ma5_signal_count/ma5_total*100:.1f}%)")


if __name__ == "__main__":
    main()
