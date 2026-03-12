#!/usr/bin/env python3
"""分析各���块量比和涨跌幅的分位数"""
import pandas as pd
import numpy as np
from datetime import datetime

# 读取数据
df = pd.read_csv('data/sector-cache.csv')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(['sector', 'date'])

# 存储结果
results = []
detailed_records = []

# 对每个板块计算
for sector in df['sector'].unique():
    sector_df = df[df['sector'] == sector].copy()

    if len(sector_df) < 10:
        continue

    # 计算MA3
    sector_df = sector_df.sort_values('date')
    sector_df['MA3_Amount'] = sector_df['amount'].rolling(window=3, min_periods=1).mean()

    # 计算量比 = 当日amount / MA3
    sector_df['Volume_Ratio'] = sector_df['amount'] / sector_df['MA3_Amount']

    # 计算涨跌幅
    sector_df['Pct_Change'] = sector_df['pct']

    # 过滤异常值（量比>3或<0.3视为异常）
    sector_df_clean = sector_df[
        (sector_df['Volume_Ratio'] > 0.3) &
        (sector_df['Volume_Ratio'] < 3.0) &
        (sector_df['amount'] > 1e10)  # amount不能太小
    ].copy()

    # 计算分位数（用最近60天的有效数据）
    recent = sector_df_clean.tail(60)
    if len(recent) < 10:
        print(f'警告: {sector} 有效数据不足{len(recent)}天')
        continue

    # 量比分位数
    vr_80 = recent['Volume_Ratio'].quantile(0.8)
    vr_60 = recent['Volume_Ratio'].quantile(0.6)
    vr_40 = recent['Volume_Ratio'].quantile(0.4)
    vr_20 = recent['Volume_Ratio'].quantile(0.2)
    vr_mean = recent['Volume_Ratio'].mean()
    vr_std = recent['Volume_Ratio'].std()

    # 涨跌幅分位数
    pct_80 = recent['Pct_Change'].quantile(0.8)
    pct_60 = recent['Pct_Change'].quantile(0.6)
    pct_40 = recent['Pct_Change'].quantile(0.4)
    pct_20 = recent['Pct_Change'].quantile(0.2)
    pct_mean = recent['Pct_Change'].mean()
    pct_std = recent['Pct_Change'].std()

    # 最新一天的有效数据（倒序找第一个有效的）
    for i in range(len(sector_df_clean) - 1, -1, -1):
        row = sector_df_clean.iloc[i]
        if pd.notna(row['Volume_Ratio']) and 0.3 < row['Volume_Ratio'] < 3.0:
            latest = row
            break
    else:
        continue

    latest_date = latest['date'].strftime('%Y-%m-%d')
    latest_vr = latest['Volume_Ratio']
    latest_pct = latest['Pct_Change']

    # 判断最新数据位于哪个分位
    vr_quantile = (recent['Volume_Ratio'] < latest_vr).sum() / len(recent)
    pct_quantile = (recent['Pct_Change'] < latest_pct).sum() / len(recent)

    results.append({
        '板块': sector,
        '最新日期': latest_date,
        '量比_80分位': f'{vr_80:.3f}',
        '量比_60分位': f'{vr_60:.3f}',
        '量比_40分位': f'{vr_40:.3f}',
        '量比_20分位': f'{vr_20:.3f}',
        '量比_均值': f'{vr_mean:.3f}',
        '量比_标准差': f'{vr_std:.3f}',
        '最新_量比': f'{latest_vr:.3f}',
        '最新_量比分位': f'{vr_quantile*100:.0f}%',
        '涨跌_80分位': f'{pct_80:.2f}%',
        '涨跌_60分位': f'{pct_60:.2f}%',
        '涨跌_40分位': f'{pct_40:.2f}%',
        '涨跌_20分位': f'{pct_20:.2f}%',
        '涨跌_均值': f'{pct_mean:.2f}%',
        '涨跌_标准差': f'{pct_std:.2f}%',
        '最新_涨跌': f'{latest_pct:.2f}%',
        '最新_涨跌分位': f'{pct_quantile*100:.0f}%'
    })

    # 保存详细记录（用于验证）
    for _, row in recent.tail(10).iterrows():
        vr_q = (recent['Volume_Ratio'] < row['Volume_Ratio']).sum() / len(recent)
        pct_q = (recent['Pct_Change'] < row['Pct_Change']).sum() / len(recent)
        detailed_records.append({
            '板块': sector,
            '日期': row['date'].strftime('%Y-%m-%d'),
            '量比': f'{row["Volume_Ratio"]:.3f}',
            '量比分位': f'{vr_q*100:.0f}%',
            '涨跌幅': f'{row["Pct_Change"]:.2f}%',
            '涨跌分位': f'{pct_q*100:.0f}%'
        })

# 转为DataFrame并显示
result_df = pd.DataFrame(results)

print('\n=== 量比分位数统计（过滤异常值后）===')
vr_cols = ['板块', '最新日期', '量比_80分位', '量比_60分位', '量比_40分位', '量比_20分位', '量比_均值', '量比_标准差', '最新_量比', '最新_量比分位']
print(result_df[vr_cols].to_string(index=False))

print('\n\n=== 涨跌幅分位数统计（过滤异常值后）===')
pct_cols = ['板块', '最新日期', '涨跌_80分位', '涨跌_60分位', '涨跌_40分位', '涨跌_20分位', '涨跌_均值', '涨跌_标准差', '最新_涨跌', '最新_涨跌分位']
print(result_df[pct_cols].to_string(index=False))

print('\n\n=== 具体日期验证数据（每个板块最近10天）===')
detail_df = pd.DataFrame(detailed_records)
for sector in detail_df['板块'].unique():
    print(f'\n【{sector}】')
    sector_detail = detail_df[detail_df['板块'] == sector]
    print(sector_detail[['日期', '量比', '量比分位', '涨跌幅', '涨跌分位']].to_string(index=False))

# 保存到文件
result_df.to_csv('data/sector_quantile_analysis.csv', index=False, encoding='utf-8-sig')
detail_df.to_csv('data/sector_daily_detail.csv', index=False, encoding='utf-8-sig')
print('\n数据已保存:')
print('- 汇总: data/sector_quantile_analysis.csv')
print('- 详细: data/sector_daily_detail.csv')
