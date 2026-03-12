#!/usr/bin/env python3
"""使用AkShare查询ETF历史数据"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

def check_etf_with_akshare(code):
    """使用AkShare检查ETF数据"""
    try:
        # 使用AkShare的基金接口
        df = ak.fund_etf_hist_sina(symbol=code)

        if df is not None and not df.empty:
            df = df.sort_values('date')
            latest_date = df['date'].iloc[-1]
            oldest_date = df['date'].iloc[0]
            data_count = len(df)

            return {
                'code': code,
                'status': '有数据',
                'latest_date': latest_date,
                'oldest_date': oldest_date,
                'data_count': data_count,
                'columns': list(df.columns)
            }
        else:
            return {
                'code': code,
                'status': '无数据'
            }
    except Exception as e:
        return {
            'code': code,
            'status': f'请求失败: {str(e)}'
        }

# 7个核心ETF
core_etfs = {
    '半导体': '512480',
    '云计算': '516510',
    '新能源': '516160',
    '商业航天': '516610',
    '创新药': '512690',
    '有色金属': '512400',
    '通讯设备': '515880'
}

print("=" * 80)
print("使用AkShare查询7个核心ETF数据")
print("=" * 80)

for name, code in core_etfs.items():
    result = check_etf_with_akshare(code)
    print(f"\n{name} ({code}):")
    if result['status'] == '有数据':
        print(f"  最新日期: {result['latest_date']}")
        print(f"  最旧日期: {result['oldest_date']}")
        print(f"  数据条数: {result['data_count']}天")
        print(f"  字段: {result['columns']}")
    else:
        print(f"  状态: {result['status']}")
