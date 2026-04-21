#!/usr/bin/env python3
"""使用东财接口查询ETF数据"""
import requests
import json

def check_etf_eastmoney(code):
    """使用东财接口查询ETF"""
    # 尝试多种东财接口
    apis = [
        # 接口1：东方财富ETF行情
        f'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f13,f14,f2,f3,f4,f5,f6',
        # 接口2：历史数据
        f'https://push2.eastmoney.com/api/qt/stock/klt?secid=1.{code}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58&klt=101&fqt=0&end=20500101&lmt=120',
        # 接口3：上交所/深交所格式
    ]

    # 判断交易所
    if code.startswith('5'):
        # 上交所：secid=1.XXXXXX
        secid = f'1.{code}'
    elif code.startswith('1'):
        # 深交所：secid=0.XXXXXX
        secid = f'0.{code}'
    else:
        secid = f'1.{code}'

    # 尝试获取历史数据
    url = f'https://push2.eastmoney.com/api/qt/stock/klt?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58&klt=101&fqt=0&end=20500101&lmt=10'

    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if data.get('rc') == 0 and 'data' in data:
            klines = data['data'].get('total', 0)
            if klines > 0:
                items = data['data'].get('items', [])
                if items:
                    latest = items[0]
                    oldest = items[-1] if len(items) > 1 else latest

                    return {
                        'code': code,
                        'secid': secid,
                        'status': '有数据',
                        'data_count': klines,
                        'latest_sample': latest,
                        'oldest_sample': oldest
                    }
        return {
            'code': code,
            'secid': secid,
            'status': '无数据',
            'response': data
        }
    except Exception as e:
        return {
            'code': code,
            'secid': secid,
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

# 其他ETF
other_etfs = {
    '芯片ETF': '159995',
    '光伏ETF': '515790',
    '军工ETF': '512660',
    '证券ETF': '512880',
    '创业板ETF': '159915'
}

print("=" * 80)
print("使用东财接口查询ETF数据")
print("=" * 80)

for name, code in core_etfs.items():
    result = check_etf_eastmoney(code)
    print(f"\n{name} ({code}):")
    print(f"  secid: {result.get('secid')}")
    if result['status'] == '有数据':
        print(f"  状态: {result['status']}")
        print(f"  数据条数: {result['data_count']}")
    else:
        print(f"  状态: {result['status']}")

print("\n" + "=" * 80)
print("其他ETF测试")
print("=" * 80)

for name, code in other_etfs.items():
    result = check_etf_eastmoney(code)
    print(f"\n{name} ({code}):")
    print(f"  secid: {result.get('secid')}")
    if result['status'] == '有数据':
        print(f"  状态: {result['status']}")
        print(f"  数据条数: {result['data_count']}")
    else:
        print(f"  状态: {result['status']}")
