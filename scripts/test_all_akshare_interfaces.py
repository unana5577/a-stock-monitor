#!/usr/bin/env python3
"""
全面测试AkShare所有ETF接口
"""
import akshare as ak
import pandas as pd
from datetime import datetime
import time

def test_all_akshare_interfaces(etf_code):
    """
    测试AkShare所有可能的ETF接口
    """
    print(f"\n{'='*80}")
    print(f"测试 {etf_code} 的所有AkShare接口")
    print(f"{'='*80}")

    results = {}

    # 接口1: fund_etf_hist_sina - 新浪ETF历史
    print(f"\n1️⃣ fund_etf_hist_sina (新浪ETF):")
    try:
        df = ak.fund_etf_hist_sina(symbol=etf_code)
        if df is not None and not df.empty:
            print(f"  ✅ 成功获取数据: {len(df)}条")
            print(f"     列名: {list(df.columns)}")
            print(f"     起始: {df.iloc[0]['日期'] if '日期' in df.columns else 'N/A'}")
            results['sina'] = {'status': 'success', 'count': len(df)}
        else:
            print(f"  ❌ 返回空数据")
            results['sina'] = {'status': 'empty'}
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results['sina'] = {'status': 'error', 'error': str(e)}

    time.sleep(1)

    # 接口2: fund_etf_hist_em - 东财ETF历史
    print(f"\n2️⃣ fund_etf_hist_em (东财ETF):")
    try:
        df = ak.fund_etf_hist_em(symbol=etf_code, period="daily", start_date="20250101", end_date="20261231", adjust="qfq")
        if df is not None and not df.empty:
            print(f"  ✅ 成功获取数据: {len(df)}条")
            print(f"     列名: {list(df.columns)}")
            if '净值日期' in df.columns:
                print(f"     起始: {df.iloc[0]['净值日期']}")
                print(f"     结束: {df.iloc[-1]['净值日期']}")
            elif 'date' in df.columns:
                print(f"     起始: {df.iloc[0]['date']}")
                print(f"     结束: {df.iloc[-1]['date']}")
            results['em'] = {'status': 'success', 'count': len(df)}
        else:
            print(f"  ❌ 返回空数据")
            results['em'] = {'status': 'empty'}
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results['em'] = {'status': 'error', 'error': str(e)}

    time.sleep(1)

    # 接口3: fund_name_em - 东财ETF信息查询
    print(f"\n3️⃣ fund_name_em (东财ETF信息):")
    try:
        df = ak.fund_name_em(fund_etf=etf_code)
        if df is not None and not df.empty:
            print(f"  ✅ 成功获取信息")
            print(f"     数据类型: {type(df)}")
            if hasattr(df, 'head'):
                print(f"     内容预览:\n{df.head()}")
            results['info'] = {'status': 'success', 'data': df}
        else:
            print(f"  ❌ 返回空数据")
            results['info'] = {'status': 'empty'}
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results['info'] = {'status': 'error', 'error': str(e)}

    time.sleep(1)

    # 接口4: fund_etf_spot_em - 东财ETF现货
    print(f"\n4️⃣ fund_etf_spot_em (东财ETF现货):")
    try:
        df = ak.fund_etf_spot_em(symbol=etf_code)
        if df is not None and not df.empty:
            print(f"  ✅ 成功获取数据: {len(df)}条")
            print(f"     列名: {list(df.columns)}")
            results['spot'] = {'status': 'success', 'count': len(df)}
        else:
            print(f"  ❌ 返回空数据")
            results['spot'] = {'status': 'empty'}
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results['spot'] = {'status': 'error', 'error': str(e)}

    time.sleep(1)

    # 接口5: 尝试作为股票查询
    print(f"\n5️⃣ stock_zh_a_hist (A股历史接口):")
    try:
        df = ak.stock_zh_a_hist(symbol=etf_code, period="daily", start_date="20250101", end_date="20261231", adjust="qfq")
        if df is not None and not df.empty:
            print(f"  ✅ 成功获取数据: {len(df)}条")
            print(f"     列名: {list(df.columns)}")
            if '日期' in df.columns:
                print(f"     起始: {df.iloc[0]['日期']}")
                print(f"     结束: {df.iloc[-1]['日期']}")
            results['stock_hist'] = {'status': 'success', 'count': len(df)}
        else:
            print(f"  ❌ 返回空数据")
            results['stock_hist'] = {'status': 'empty'}
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results['stock_hist'] = {'status': 'error', 'error': str(e)}

    time.sleep(1)

    # 接口6: fund_etf_category_sina - 新浪ETF分类
    print(f"\n6️⃣ fund_etf_category_sina (新浪ETF分类):")
    try:
        df = ak.fund_etf_category_sina(symbol="ETF基金")
        if df is not None and not df.empty:
            print(f"  ✅ 成功获取ETF分类列表")
            # 查找目标ETF
            if '代码' in df.columns:
                matched = df[df['代码'].str.contains(etf_code, na=False)]
                if not matched.empty:
                    print(f"  ✅ 找到该ETF:")
                    print(f"     {matched.to_string()}")
                else:
                    print(f"  ⚠️ 未找到该ETF代码")
            results['category'] = {'status': 'success', 'found': not matched.empty}
        else:
            print(f"  ❌ 返回空数据")
            results['category'] = {'status': 'empty'}
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results['category'] = {'status': 'error', 'error': str(e)}

    return results

# 测试所有问题ETF
problem_etfs = {
    '半导体': 'sh512480',
    '新能源': 'sh516160',
    '创新药': 'sh512690',
    '有色金属': 'sh512400',
    '通讯设备': 'sh515880'
}

print("="*80)
print("AkShare所有接口全面测试")
print("="*80)

all_results = {}

for sector, code in problem_etfs.items():
    print(f"\n\n{'#'*80}")
    print(f"# 测试板块: {sector} ({code})")
    print(f"{'#'*80}")
    results = test_all_akshare_interfaces(code)
    all_results[sector] = results

    # 总结该ETF的结果
    success_count = sum(1 for r in results.values() if r.get('status') == 'success')
    print(f"\n📊 {sector} 总结: {success_count}/6 个接口成功")

# 最终汇总
print(f"\n\n{'='*80}")
print("最终汇总")
print(f"{'='*80}")

for sector, results in all_results.items():
    print(f"\n{sector}:")
    for interface, result in results.items():
        status = result.get('status')
        if status == 'success':
            print(f"  ✅ {interface}: 成功")
        elif status == 'empty':
            print(f"  ❌ {interface}: 无数据")
        elif status == 'error':
            print(f"  ❌ {interface}: 错误")
