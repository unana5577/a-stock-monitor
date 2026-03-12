#!/usr/bin/env python3
"""
ETF上市时间与数据源全面排查
"""
import sys
import os
import requests
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入数据获取函数
from fetch_sector_data import _normalize_etf_code, _fetch_tencent_daily, _fetch_ashare_daily

def check_etf_list_date(etf_code):
    """
    查询ETF上市时间
    """
    print(f"\n查询 {etf_code} 上市时间...")

    # 方法1：通过东方财富查询
    try:
        # 判断交易所
        if etf_code.startswith('5'):
            full_code = f'1.{etf_code}'  # 上交所
        else:
            full_code = f'0.{etf_code}'  # 深交所

        url = f'https://push2.eastmoney.com/api/qt/stock/get?secid={full_code}&fields=f120,f121,f122,f174,f175'
        resp = requests.get(url, timeout=10)
        data = resp.json()

        if data.get('rc') == 0 and 'data' in data:
            info = data['data']
            list_date = info.get('f120')  # 上市日期 f120格式: 20241213
            if list_date:
                list_date_str = str(list_date)
                if len(list_date_str) == 8:
                    formatted = f"{list_date_str[0:4]}-{list_date_str[4:6]}-{list_date_str[6:8]}"
                    print(f"  上市时间: {formatted}")
                    return formatted

        print(f"  ⚠️ 东财未找到上市信息")
        return None
    except Exception as e:
        print(f"  ❌ 查询失败: {e}")
        return None

def check_all_data_sources(etf_code, target_start_date="2025-05-19"):
    """
    测试所有数据源
    """
    print(f"\n{'='*60}")
    print(f"测试 {etf_code} 数据源")
    print(f"目标起始日期: {target_start_date}")
    print(f"{'='*60}")

    normalized_code = _normalize_etf_code(etf_code)
    print(f"标准化代码: {normalized_code}")

    results = {}

    # 测试1：腾讯API
    print(f"\n1️⃣ 腾讯API测试:")
    try:
        tencent_result = _fetch_tencent_daily(normalized_code, limit=365)
        if tencent_result.get("data") and len(tencent_result["data"]) > 0:
            data = tencent_result["data"]
            start_date = data[0]["date"]
            end_date = data[-1]["date"]
            count = len(data)

            # 检查是否满足起始日期要求
            meets_requirement = start_date <= target_start_date

            print(f"  ✅ 有数据: {count}天")
            print(f"  范围: {start_date} 至 {end_date}")
            print(f"  是否满足要求: {'✅' if meets_requirement else '❌'} 需要从{target_start_date}开始，实际从{start_date}开始")

            results['tencent'] = {
                'status': 'success',
                'start_date': start_date,
                'end_date': end_date,
                'count': count,
                'meets_requirement': meets_requirement
            }
        else:
            print(f"  ❌ 无数据")
            results['tencent'] = {'status': 'no_data'}
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        results['tencent'] = {'status': 'error', 'error': str(e)}

    # 测试2：Ashare
    print(f"\n2️⃣ Ashare测试:")
    try:
        ashare_result = _fetch_ashare_daily(etf_code, limit=365)
        if ashare_result.get("data") and len(ashare_result["data"]) > 0:
            data = ashare_result["data"]
            if isinstance(data, list) and len(data) > 0:
                # Ashare返回的可能是DataFrame或其他格式
                if hasattr(data[0], 'get'):
                    start_date = data[0].get('date', 'N/A')
                    end_date = data[-1].get('date', 'N/A')
                else:
                    start_date = 'N/A'
                    end_date = 'N/A'
                count = len(data)

                # 简单检查
                meets_requirement = start_date != 'N/A' and start_date <= target_start_date

                print(f"  ✅ 有数据: {count}天")
                print(f"  范围: {start_date} 至 {end_date}")
                print(f"  是否满足要求: {'✅' if meets_requirement else '❌'}")

                results['ashare'] = {
                    'status': 'success',
                    'start_date': start_date,
                    'end_date': end_date,
                    'count': count,
                    'meets_requirement': meets_requirement
                }
            else:
                print(f"  ❌ 无数据")
                results['ashare'] = {'status': 'no_data'}
        else:
            print(f"  ❌ 无数据")
            results['ashare'] = {'status': 'no_data'}
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        results['ashare'] = {'status': 'error', 'error': str(e)}

    return results

def generate_summary_report(etf_configs):
    """
    生成汇总报告
    """
    print("\n" + "="*80)
    print("ETF数据源排查汇总报告")
    print("="*80)

    summary = []

    for sector, etf_code in etf_configs.items():
        print(f"\n{'─'*80}")
        print(f"板块: {sector} ({etf_code})")
        print(f"{'─'*80}")

        # 1. 查询上市时间
        list_date = check_etf_list_date(etf_code)

        # 2. 测试数据源
        data_sources = check_all_data_sources(etf_code)

        # 3. 分析
        print(f"\n📊 分析结果:")

        # 判断上市时间是否满足要求
        if list_date:
            if list_date > "2025-05-19":
                print(f"  ⚠️ ETF上市时间({list_date})晚于要求起始日期(2025-05-19)")
                print(f"  ⚠️ 这是正常情况，前面无数据是合理的")
                status = "上市晚，数据合理"
            else:
                print(f"  ✅ ETF上市时间({list_date})早于要求起始日期")
                status = "上市早，应该有数据"
        else:
            print(f"  ❌ 无法查询上市时间")
            status = "无法查询"

        # 判断数据源状态
        tencent_ok = data_sources.get('tencent', {}).get('status') == 'success'
        ashare_ok = data_sources.get('ashare', {}).get('status') == 'success'

        if tencent_ok or ashare_ok:
            if tencent_ok:
                meets = data_sources['tencent']['meets_requirement']
                if meets:
                    print(f"  ✅ 腾讯API数据满足要求")
                else:
                    print(f"  ⚠️ 腾讯API有数据但不满足起始日期要求")

            if ashare_ok:
                meets = data_sources['ashare']['meets_requirement']
                if meets:
                    print(f"  ✅ Ashare数据满足要求")
                else:
                    print(f"  ⚠️ Ashare有数据但不满足起始日期要求")
        else:
            print(f"  ❌ 所有数据源均无数据")
            print(f"  ❌ 可能原因:")
            print(f"     1. ETF代码错误")
            print(f"     2. 数据源不支持该ETF")
            print(f"     3. 网络问题")

        summary.append({
            'sector': sector,
            'code': etf_code,
            'list_date': list_date,
            'tencent_status': data_sources.get('tencent', {}).get('status', 'N/A'),
            'ashare_status': data_sources.get('ashare', {}).get('status', 'N/A'),
            'overall_status': status
        })

    # 最终汇总
    print(f"\n\n{'='*80}")
    print("最终汇总")
    print(f"{'='*80}")

    for item in summary:
        print(f"\n{item['sector']} ({item['code']}):")
        print(f"  上市时间: {item['list_date']}")
        print(f"  腾讯API: {item['tencent_status']}")
        print(f"  Ashare:  {item['ashare_status']}")
        print(f"  整体判断: {item['overall_status']}")

if __name__ == "__main__":
    # 用户原始的ETF配置
    etf_configs = {
        '半导体': '512480',
        '云计算': '516510',
        '新能源': '516160',
        '商业航天': '516610',
        '创新药': '512690',
        '有色金属': '512400',
        '通讯设备': '515880'
    }

    generate_summary_report(etf_configs)
