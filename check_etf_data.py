#!/usr/bin/env python3
"""查询ETF历史数据可用性"""
import requests
import json
from datetime import datetime

def check_etf_data(code, code_type="etf"):
    """检查单个ETF的数据可用性"""
    # 判断交易所
    if code.startswith('5'):
        full_code = f'sh{code}'
        exchange = '上交所'
    else:
        full_code = f'sz{code}'
        exchange = '深交所'

    # 尝试获取最近180天数据
    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full_code},day,,,180,qfq'

    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if data.get('data') and full_code in data['data']:
            rows = data['data'][full_code].get('day', [])
            if rows:
                # rows是按时间倒序排列的
                latest_date = rows[0][0]
                oldest_date = rows[-1][0]
                data_count = len(rows)

                return {
                    'code': code,
                    'full_code': full_code,
                    'exchange': exchange,
                    'status': '有数据',
                    'latest_date': latest_date,
                    'oldest_date': oldest_date,
                    'data_count': data_count
                }
            else:
                return {
                    'code': code,
                    'full_code': full_code,
                    'exchange': exchange,
                    'status': '无数据'
                }
        else:
            return {
                'code': code,
                'full_code': full_code,
                'exchange': exchange,
                'status': 'API返回异常'
            }
    except Exception as e:
        return {
            'code': code,
            'full_code': full_code,
            'exchange': exchange,
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

# 其他常见ETF
other_etfs = {
    '芯片ETF': '159995',
    '半导体设备': '562980',
    '光伏ETF': '515790',
    '军工ETF': '512660',
    '医药ETF': '512010',
    '证券ETF': '512880',
    '银行ETF': '512800',
    '创业板ETF': '159915',
    '科创50ETF': '588000',
    '沪深300ETF': '510300'
}

print("=" * 80)
print("7个核心ETF数据查询结果")
print("=" * 80)

for name, code in core_etfs.items():
    result = check_etf_data(code)
    print(f"\n{name} ({code}):")
    if result['status'] == '有数据':
        print(f"  交易所: {result['exchange']}")
        print(f"  最新日期: {result['latest_date']}")
        print(f"  最旧日期: {result['oldest_date']}")
        print(f"  数据条数: {result['data_count']}天")
    else:
        print(f"  状态: {result['status']}")

print("\n" + "=" * 80)
print("其他常见ETF数据查询结果")
print("=" * 80)

for name, code in other_etfs.items():
    result = check_etf_data(code)
    print(f"\n{name} ({code}):")
    if result['status'] == '有数据':
        print(f"  交易所: {result['exchange']}")
        print(f"  最新日期: {result['latest_date']}")
        print(f"  最旧日期: {result['oldest_date']}")
        print(f"  数据条数: {result['data_count']}天")
    else:
        print(f"  状态: {result['status']}")
