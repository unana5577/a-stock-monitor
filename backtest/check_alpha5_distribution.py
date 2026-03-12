#!/usr/bin/env python3
"""分析Alpha_5分布（使用基准指数）"""
import sys
import json
import pandas as pd
import numpy as np
sys.path.insert(0, '.')

from sector_lifecycle import calculate_alpha_n_days

# 加载数据
with open('data/etf_daily/etf_backfill_2026-03-09.json', 'r') as f:
    data = json.load(f)

# 尝试找到基准指数（如果有）
benchmark_keys = [k for k in data.keys() if any(x in k for x in ['指数', '300', '创业板', '科创', '上证'])]
print(f"可用的基准: {benchmark_keys[:3]}...")

# 使用半导体数据
records = [{'date': pd.to_datetime(r['date']), 'close': float(r['close'])}
           for r in data['半导体']['data']]
df = pd.DataFrame(records).sort_values('date').reset_index(drop=True)

# 统计Alpha_5分布（用简单的5日收益率代替Alpha，因为没有基准）
returns_5 = []
for i in range(60, min(250, len(df))):
    sector_cut = df.iloc[:i+1]
    if len(sector_cut) >= 6:
        ret_5 = (sector_cut['close'].iloc[-1] - sector_cut['close'].iloc[-6]) / sector_cut['close'].iloc[-6] * 100
        returns_5.append(ret_5)

returns_5 = np.array(returns_5)
print(f'\n5日收益率分布（代替Alpha_5）:')
print(f'样本数: {len(returns_5)}')
print(f'范围: {returns_5.min():.2f}% ~ {returns_5.max():.2f}%')
print(f'平均: {returns_5.mean():.2f}%')
print(f'标准差: {returns_5.std():.2f}%')

print(f'\n【文档阈值命中情况】')
print(f' > 3% (强势向上): {(returns_5 > 3).sum()} ({(returns_5 > 3).sum()/len(returns_5)*100:.1f}%)')
print(f' > 1% (偏强向上): {(returns_5 > 1).sum()} ({(returns_5 > 1).sum()/len(returns_5)*100:.1f}%)')
print(f' -1%~1% (中性震荡): {((returns_5 >= -1) & (returns_5 <= 1)).sum()} ({((returns_5 >= -1) & (returns_5 <= 1)).sum()/len(returns_5)*100:.1f}%)')
print(f' < -3% (弱势向下): {(returns_5 < -3).sum()} ({(returns_5 < -3).sum()/len(returns_5)*100:.1f}%)')

print(f'\n【分位数阈值】')
print(f'70%分位: {np.percentile(returns_5, 70):.2f}%')
print(f'60%分位: {np.percentile(returns_5, 60):.2f}%')
print(f'50%分位: {np.percentile(returns_5, 50):.2f}%')
print(f'40%分位: {np.percentile(returns_5, 40):.2f}%')
print(f'30%分位: {np.percentile(returns_5, 30):.2f}%')

print(f'\n【结论】')
print(f'如果用文档阈值（>3%）, 只能捕捉 {(returns_5 > 3).sum()/len(returns_5)*100:.1f}% 的强势向上机会')
print(f'如果用70%分位({np.percentile(returns_5, 70):.2f}%), 可以捕捉 30% 的相对强势机会')
