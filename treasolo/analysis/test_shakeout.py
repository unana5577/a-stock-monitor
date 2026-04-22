import json
import pandas as pd
import numpy as np
from pathlib import Path

# 读取通讯设备(CPO) ETF的日线数据
file_path = Path("data/etf/daily/sh515880/daily.jsonl")

records = []
with open(file_path, "r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            records.append(json.loads(line))

# 转为DataFrame并取近120天
df = pd.DataFrame(records)
df = df.tail(120).copy().reset_index(drop=True)

# 计算昨日收盘价和各项跌幅指标
df['prev_close'] = df['close'].shift(1)
# 第一天的prev_close用pct倒推
if df['pct'].iloc[0] != 0:
    df.loc[0, 'prev_close'] = df['close'].iloc[0] / (1 + df['pct'].iloc[0] / 100)
else:
    df.loc[0, 'prev_close'] = df['close'].iloc[0]

# 计算每日盘中最大跌幅 (最低价相对于昨收的跌幅)
df['min_pct'] = (df['low'] - df['prev_close']) / df['prev_close'] * 100

# 剔除无效数据
df = df.dropna(subset=['min_pct'])

# 计算P20和P10防线 (注意min_pct是负数，P20代表只有20%的日子跌得比这个深)
# 用 quantile(0.2) 算出来就是那个负数分位数
p20_line = df['min_pct'].quantile(0.2)
p10_line = df['min_pct'].quantile(0.1)

print(f"【通讯设备 (sh515880) 近120天回撤防线】")
print(f"日常回撤线 (P20): {p20_line:.2f}% (80%的日子盘中最多跌这么多)")
print(f"异常下破线 (P10): {p10_line:.2f}% (只有10%的极端日子会跌破这条线)\n")

# 寻找典型洗盘日：
# 条件1：盘中砸过盘 (min_pct < -0.5%)
# 条件2：没有跌破 P20防线 (min_pct >= P20)
# 条件3：验证洗盘成功 (未来3天累计涨幅 > 0)

print("【典型震荡洗盘日提取 (供K线对照)】")
print(f"{'日期':<12} | {'盘中最低跌幅':<10} | {'收盘涨跌幅':<10} | {'洗盘结构形态':<18} | {'未来3天累计涨跌'}")
print("-" * 75)

count = 0
for i in range(len(df) - 3):
    row = df.iloc[i]
    if not row['date'].startswith('2026'):
        continue
        
    min_pct = row['min_pct']
    close_pct = row['pct']
    
    # 计算下影线大小 (收盘和开盘的较小值 - 最低价)
    min_open_close = min(row['open'], row['close'])
    lower_wick = (min_open_close - row['low']) / row['prev_close'] * 100
    
    # 计算盘中最大反抽幅度 (最高价 - 最低价) -> 衡量深V洗盘的空间
    max_rebound = (row['high'] - row['low']) / row['prev_close'] * 100
    
    # 模拟盘中判定条件
    if min_pct < -0.5 and min_pct >= p20_line:
        # 计算未来3天的累计涨跌
        future_3_close = df.iloc[i+3]['close']
        future_ret = (future_3_close - row['close']) / row['close'] * 100
        
        # 结构确认 (由于我们只有日线，我们用下影线和全天振幅来粗略模拟盘中这两种洗盘结构的最终结果)
        # 1. 空间确认(深V): 盘中砸盘后拉起超过 0.8% (下影线够长)
        is_deep_v = lower_wick >= 0.4
        
        # 2. 时间确认(横盘): 盘中跌了，但全天振幅较小(上下3.0%以内)，说明跌下去后死气沉沉横盘了一天
        is_flat_shakeout = (max_rebound <= 3.0) and not is_deep_v
        
        if future_ret > abs(min_pct) * 1.5:  
            struct_type = "深V洗盘(拉起>0.4%)" if is_deep_v else "横盘洗盘(全天振幅<3.0%)"
            print(f"{row['date']:<12} | {min_pct:>8.2f}%   | {close_pct:>8.2f}%   | {struct_type:<18} | 涨 {future_ret:.2f}%")
            count += 1
            if count >= 8:  # 挑8个典型日子
                break

print("-" * 75)
last_date = df.iloc[-1]['date']
print(f"\n【近期/今日 ({last_date}) 判定情况】")
for i in range(max(0, len(df) - 5), len(df)):
    row = df.iloc[i]
    min_pct = row['min_pct']
    close_pct = row['pct']
    min_open_close = min(row['open'], row['close'])
    lower_wick = (min_open_close - row['low']) / row['prev_close'] * 100
    max_rebound = (row['high'] - row['low']) / row['prev_close'] * 100
    
    is_deep_v = lower_wick >= 0.4
    is_flat_shakeout = (max_rebound <= 3.0) and not is_deep_v
    
    status = "跌破防线(异常弱势)"
    if min_pct >= p20_line:
        if min_pct >= -0.5:
            status = "强势未砸盘(不算洗盘)"
        elif is_deep_v:
            status = "深V洗盘(拉起>0.4%)"
        elif is_flat_shakeout:
            status = "横盘洗盘(全天振幅<3.0%)"
        else:
            status = "震荡(结构未确认)"
            
    print(f"{row['date']:<12} | {min_pct:>8.2f}%   | {close_pct:>8.2f}%   | {status:<18}")
