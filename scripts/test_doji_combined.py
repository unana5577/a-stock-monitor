#!/usr/bin/env python3
"""测试"缩量后首次放量 + 十字星"组合信号"""
import pandas as pd
import numpy as np

def recognize_kline(open_price, close, high, low):
    """识别K线形态"""
    if open_price == 0:
        return "普通K线", 0

    body = abs(close - open_price)
    body_pct = body / open_price * 100

    # 十字星：涨跌幅 < 1%
    if body_pct < 1.0:
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low

        if lower_shadow > upper_shadow * 2:
            return "锤子线", body_pct
        if upper_shadow > lower_shadow * 2:
            return "射击之星", body_pct
        return "十字星", body_pct

    return "其他", body_pct


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
test_sectors = ['半导体', '云计算', '新能源', '创新药', '有色金属']

print("=" * 80)
print("组合信号测试：缩量后首次放量 + 十字星")
print("=" * 80)

all_results = []

for sector in test_sectors:
    sector_df = df[df['sector'] == sector].copy()

    if len(sector_df) < 20:
        continue

    # 计算量比和K线形态
    volume_ratios = []
    kline_types = []

    for i in range(len(sector_df)):
        vr = calculate_volume_ratio(sector_df, i, window=3)
        volume_ratios.append(vr if vr else 1.0)

        row = sector_df.iloc[i]
        ktype, _ = recognize_kline(row['open'], row['close'], row['high'], row['low'])
        kline_types.append(ktype)

    sector_df = sector_df.copy()
    sector_df['量比'] = volume_ratios
    sector_df['K线形态'] = kline_types

    # 过滤异常量比
    sector_df.loc[sector_df['量比'] > 3.0, '量比'] = np.nan
    sector_df.loc[sector_df['量比'] < 0.3, '量比'] = np.nan

    # 计算历史量比分位数
    sector_df['量比60分位'] = sector_df['量比'].rolling(window=60, min_periods=20).quantile(0.6)
    sector_df['量比80分位'] = sector_df['量比'].rolling(window=60, min_periods=20).quantile(0.8)

    # 找出所有十字星
    doji_days = sector_df[sector_df['K线形态'].isin(['十字星', '锤子线', '射击之星'])].copy()

    if len(doji_days) == 0:
        continue

    print(f"\n{'=' * 80}")
    print(f"板块: {sector} (共{len(doji_days)}个十字星)")
    print('=' * 80)

    # 测试组合信号
    combined_signals = []

    for idx, doji in doji_days.iterrows():
        doji_idx = sector_df.index.get_loc(idx)
        doji_date = doji['date'].strftime('%Y-%m-%d')
        doji_type = doji['K线形态']
        doji_vr = doji['量比']

        # 检查前3日是否缩量（量比 < 60分位）
        shrink_count = 0
        for i in range(max(0, doji_idx - 3), doji_idx):
            row = sector_df.iloc[i]
            vr_60 = row['量比60分位']
            vr = row['量比']
            if pd.notna(vr_60) and pd.notna(vr) and vr < vr_60:
                shrink_count += 1

        # 如果前3日至少有2天缩量，则认为满足"缩量后"条件
        is_shrink_before = shrink_count >= 2

        # 检查次日是否首次放量（需要次日数据）
        if doji_idx + 1 >= len(sector_df):
            continue

        next_day = sector_df.iloc[doji_idx + 1]
        next_vr = next_day['量比']
        next_vr_80 = doji['量比80分位']  # 用十字星当天的80分位
        next_pct = next_day['pct']

        is_first_expand = pd.notna(next_vr) and pd.notna(next_vr_80) and next_vr > next_vr_80
        is_next_up = next_pct > 0

        # 组合信号：缩量后 + 十字星 + 次日放量上涨
        if is_shrink_before and is_first_expand and is_next_up:
            combined_signals.append({
                '板块': sector,
                '十字星日期': doji_date,
                '类型': doji_type,
                '前3日缩量天数': shrink_count,
                '当日量比': f"{doji_vr:.2f}" if pd.notna(doji_vr) else "N/A",
                '次日日期': next_day['date'].strftime('%Y-%m-%d'),
                '次日量比': f"{next_vr:.2f}",
                '80分位阈值': f"{next_vr_80:.2f}",
                '次日涨跌': f"{next_pct:+.2f}%",
                '验证结果': '✅ 成功'
            })
        elif is_shrink_before:
            # 缩量后有十字星，但次日未放量上涨
            combined_signals.append({
                '板块': sector,
                '十字星日期': doji_date,
                '类型': doji_type,
                '前3日缩量天数': shrink_count,
                '当日量比': f"{doji_vr:.2f}" if pd.notna(doji_vr) else "N/A",
                '次日日期': next_day['date'].strftime('%Y-%m-%d'),
                '次日量比': f"{next_vr:.2f}",
                '80分位阈值': f"{next_vr_80:.2f}",
                '次日涨跌': f"{next_pct:+.2f}%",
                '验证结果': '❌ 失败' if next_pct < 0 else '⚠️ 未放量'
            })

    # 显示结果
    if combined_signals:
        results_df = pd.DataFrame(combined_signals)
        print(f"\n满足\"缩量后\"条件的十字星: {len(combined_signals)}个\n")
        print(results_df.to_string(index=False))

        # 统计
        success = sum(1 for s in combined_signals if '成功' in s['验证结果'])
        total = len(combined_signals)
        success_rate = success / total * 100 if total > 0 else 0

        print(f"\n组合信号胜率: {success}/{total} = {success_rate:.1f}%")

        # 与之前对比
        all_doji = len(doji_days)
        combined_rate = len(combined_signals) / all_doji * 100 if all_doji > 0 else 0
        print(f"组合信号出现率: {len(combined_signals)}/{all_doji} = {combined_rate:.1f}%")

        all_results.append({
            '板块': sector,
            '总十字星': all_doji,
            '满足缩量条件': len(combined_signals),
            '组合信号成功': success,
            '组合信号胜率': f"{success_rate:.1f}%"
        })

# 汇总统计
print("\n" + "=" * 80)
print("汇总统计")
print("=" * 80)
summary_df = pd.DataFrame(all_results)
print(summary_df.to_string(index=False))

if len(all_results) > 0:
    avg_success = np.mean([float(r['组合信号胜率'].rstrip('%')) for r in all_results])
    print(f"\n平均胜率: {avg_success:.1f}%")
