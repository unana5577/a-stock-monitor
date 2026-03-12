#!/usr/bin/env python3
"""
深度查询ETF信息
"""
import requests
import akshare as ak
from datetime import datetime

def query_etf_info_from_sina(etf_code):
    """从新浪查询ETF基本信息"""
    try:
        # 新浪ETF接口
        url = f"http://fund.eastmoney.com/{etf_code}.html"
        # 或者用akshare
        df = ak.fund_etf_hist_sina(symbol=etf_code)
        if df is not None and not df.empty:
            return {
                'source': 'sina/akshare',
                'has_data': True,
                'count': len(df),
                'start': df.iloc[0]['日期'] if '日期' in df.columns else 'N/A'
            }
    except Exception as e:
        return {'source': 'sina/akshare', 'error': str(e)}

def query_all_sources_for_etf(etf_code):
    """测试所有可能的数据源"""
    print(f"\n深度查询 {etf_code}:")

    results = {}

    # 1. AkShare基金历史
    print(f"  测试AkShare基金接口...")
    try:
        df = ak.fund_etf_hist_sina(symbol=etf_code)
        if df is not None and not df.empty:
            print(f"  ✅ AkShare有数据: {len(df)}条")
            if '日期' in df.columns:
                print(f"     起始: {df.iloc[0]['日期']}")
                print(f"     结束: {df.iloc[-1]['日期']}")
            results['akshare_sina'] = 'success'
        else:
            print(f"  ❌ AkShare无数据")
            results['akshare_sina'] = 'no_data'
    except Exception as e:
        print(f"  ❌ AkShare失败: {e}")
        results['akshare_sina'] = f'error: {e}'

    # 2. 尝试作为股票查询（有些系统把ETF当股票处理）
    print(f"  测试股票接口...")
    try:
        # 尝试作为普通股票查询
        df = ak.stock_zh_a_hist(symbol=etf_code, period="daily", start_date="20250101", adjust="")
        if df is not None and not df.empty:
            print(f"  ✅ 股票接口有数据: {len(df)}条")
            results['stock_interface'] = 'success'
        else:
            print(f"  ❌ 股票接口无数据")
            results['stock_interface'] = 'no_data'
    except Exception as e:
        print(f"  ❌ 股票接口失败: {e}")
        results['stock_interface'] = f'error: {e}'

    # 3. 尝试Tushare（如果有token）
    print(f"  Tushare: 需要token，跳过")
    results['tushare'] = 'not_tested'

    return results

# 测试问题ETF
problem_etfs = {
    '半导体': '512480',
    '新能源': '516160',
    '创新药': '512690',
    '有色金属': '512400',
    '通讯设备': '515880'
}

print("="*80)
print("深度查询无数据ETF")
print("="*80)

for sector, code in problem_etfs.items():
    print(f"\n{'─'*80}")
    print(f"{sector} ({code})")
    print(f"{'─'*80}")
    results = query_all_sources_for_etf(code)

    # 判断结果
    if any(r == 'success' for r in results.values()):
        print(f"\n✅ 找到可用数据源")
    else:
        print(f"\n❌ 所有数据源均失败，可能原因:")
        print(f"  1. ETF代码不存在")
        print(f"  2. ETF未上市或已退市")
        print(f"  3. 数据源不支持该ETF")
