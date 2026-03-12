#!/usr/bin/env python3
"""查找可用的ETF代码"""
import requests

def test_etf_code(code):
    """测试单个ETF代码"""
    # 判断交易所
    if code.startswith('5'):
        full_code = f'sh{code}'
    else:
        full_code = f'sz{code}'

    url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={full_code},day,,,180,qfq'

    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if data.get('data') and full_code in data['data']:
            rows = data['data'][full_code].get('day', [])
            if rows:
                return {
                    'code': code,
                    'full_code': full_code,
                    'status': '✅ 有数据',
                    'latest': rows[0][0],
                    'oldest': rows[-1][0],
                    'count': len(rows)
                }
        return {'code': code, 'full_code': full_code, 'status': '❌ 无数据'}
    except:
        return {'code': code, 'full_code': full_code, 'status': '❌ 请求失败'}

# 测试可能可用的ETF代码
test_codes = {
    '半导体相关': ['512480', '159995', '584990', '562980'],
    '云计算相关': ['516510', '159857', '164888'],
    '新能源相关': ['516160', '515790', '159865'],
    '军工/商业航天': ['516610', '512660', '512680'],
    '医药相关': ['512690', '512010', '159938'],
    '有色金属': ['512400', '515880', '516780'],
    '通讯设备': ['515880', '512880', '159863']
}

print("=" * 80)
print("查找可用的ETF代码")
print("=" * 80)

available_etfs = {}

for category, codes in test_codes.items():
    print(f"\n{category}:")
    for code in codes:
        result = test_etf_code(code)
        print(f"  {code}: {result['status']}", end='')
        if result['status'] == '✅ 有数据':
            print(f" ({result['oldest']} 至 {result['latest']}, {result['count']}天)")
            available_etfs[code] = result
        else:
            print()

print("\n" + "=" * 80)
print(f"找到 {len(available_etfs)} 个可用ETF")
print("=" * 80)

# 生成推荐配置
print("\n推荐配置:")
recommendations = {
    '半导体': '159995',  # 芯片ETF
    '云计算': '516510',  # 原配置可用
    '新能源': '515790',  # 光伏ETF
    '商业航天': '516610',  # 原配置可用
    '创新药': '512010',  # 医药ETF
    '有色金属': '516780',  # 有色ETF
    '通讯设备': '512880'  # 证券ETF替代
}

for sector, code in recommendations.items():
    status = test_etf_code(code)['status']
    print(f"  {sector}: {code} {status}")
