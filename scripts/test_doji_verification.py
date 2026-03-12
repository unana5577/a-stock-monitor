#!/usr/bin/env python3
"""测试十字星验证逻辑"""
import pandas as pd
import numpy as np

def recognize_kline(open_price, close, high, low):
    """识别K线形态"""
    if open_price == 0:
        return "普通K线", 0, 0, 0

    body = abs(close - open_price)
    body_pct = body / open_price * 100

    # 上下影线长度
    upper_shadow = high - max(open_price, close)
    lower_shadow = min(open_price, close) - low

    # 十字星：涨跌幅 < 1%
    if body_pct < 1.0:
        if lower_shadow > upper_shadow * 2:
            return "锤子线", body_pct, upper_shadow, lower_shadow  # 底部信号
        if upper_shadow > lower_shadow * 2:
            return "射击之星", body_pct, upper_shadow, lower_shadow  # 顶部信号
        return "十字星", body_pct, upper_shadow, lower_shadow  # 多空均衡

    # 大阳线/大阴线：涨跌幅 > 3%
    if body_pct > 3.0:
        return "大阳线" if close > open_price else "大阴线", body_pct, upper_shadow, lower_shadow

    # 小阳线/小阴线
    return "小阳线" if close > open_price else "小阴线", body_pct, upper_shadow, lower_shadow


def calculate_volume_ratio(df, index, window=3):
    """计算量比"""
    if index < window - 1:
        return None
    current_amount = df.iloc[index]['amount']
    ma3 = df.iloc[index-window+1:index+1]['amount'].mean()
    return current_amount / ma3 if ma3 > 0 else None


# 读取数据
df = pd.read_csv('data/sector-cache.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(['sector', 'date'])

# 测试板块
test_sectors = ['半导体', '云计算', '新能源']

print("=" * 80)
print("十字星验证测试")
print("=" * 80)

for sector in test_sectors:
    sector_df = df[df['sector'] == sector].copy()

    if len(sector_df) < 20:
        continue

    print(f"\n{'=' * 80}")
    print(f"板块: {sector}")
    print('=' * 80)

    # 识别K线形态
    kline_types = []
    volume_ratios = []

    for i in range(len(sector_df)):
        row = sector_df.iloc[i]
        ktype, body_pct, upper, lower = recognize_kline(
            row['open'], row['close'], row['high'], row['low']
        )
        kline_types.append(ktype)
        vr = calculate_volume_ratio(sector_df, i, window=3)
        volume_ratios.append(vr if vr else 1.0)

    sector_df = sector_df.copy()
    sector_df['K线形态'] = kline_types
    sector_df['量比'] = volume_ratios

    # 过滤异常量比
    sector_df.loc[sector_df['量比'] > 3, '量比'] = np.nan
    sector_df.loc[sector_df['量比'] < 0.3, '量比'] = np.nan

    # 找出所有十字星
    doji_days = sector_df[sector_df['K线形态'].isin(['十字星', '锤子线', '射击之星'])].copy()

    if len(doji_days) == 0:
        print("未找到十字星形态")
        continue

    print(f"\n找到 {len(doji_days)} 个十字星形态\n")

    # 对每个十字星，验证次日表现
    verification_results = []

    for idx, doji in doji_days.iterrows():
        doji_date = doji['date'].strftime('%Y-%m-%d')
        doji_type = doji['K线形态']
        doji_close = doji['close']
        doji_pct = doji['pct']

        # 找次日数据
        doji_idx = sector_df.index.get_loc(idx)
        if doji_idx + 1 >= len(sector_df):
            continue

        next_day = sector_df.iloc[doji_idx + 1]
        next_date = next_day['date'].strftime('%Y-%m-%d')
        next_pct = next_day['pct']
        next_vr = next_day['量比']

        # 计算历史量比分位数（用于判断是否放量）
        recent_vr = sector_df['量比'].iloc[max(0, doji_idx-59):doji_idx+1].dropna()
        if len(recent_vr) < 10:
            vr_quantile = None
        else:
            vr_80 = recent_vr.quantile(0.8)
            vr_quantile = (next_vr >= vr_80) if pd.notna(next_vr) else None

        # 判断验证结果
        if vr_quantile and next_pct > 0:
            result = "✅ 企稳确认"
            detail = f"次日{next_vr:.2f}量比({vr_80:.2f}阈值) + {next_pct:+.2f}%"
        elif not vr_quantile and next_pct > 0 and pd.notna(next_vr) and next_vr > 1.0:
            result = "⚠️ 温和上涨"
            detail = f"次日{next_vr:.2f}量比 + {next_pct:+.2f}%"
        elif next_pct < 0:
            result = "❌ 继续下跌"
            detail = f"次日{next_pct:+.2f}%"
        else:
            result = "➡️ 横盘整理"
            detail = f"次日{next_pct:+.2f}%"

        verification_results.append({
            '十字星日期': doji_date,
            '类型': doji_type,
            '收盘': f"{doji_close:.2f}",
            '当日涨跌': f"{doji_pct:+.2f}%",
            '次日日期': next_date,
            '次日涨跌': f"{next_pct:+.2f}%",
            '次日量比': f"{next_vr:.2f}" if pd.notna(next_vr) else "N/A",
            '验证结果': result,
            '说明': detail
        })

    # 显示验证结果
    if verification_results:
        results_df = pd.DataFrame(verification_results)
        print(results_df.to_string(index=False))

        # 统计验证结果
        print(f"\n验证统计:")
        confirm_count = sum(1 for r in verification_results if "企稳确认" in r['验证结果'])
        total_count = len(verification_results)
        print(f"  企稳确认率: {confirm_count}/{total_count} = {confirm_count/total_count*100:.1f}%")

print("\n" + "=" * 80)
print("验证完成")
print("=" * 80)
