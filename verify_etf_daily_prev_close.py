#!/usr/bin/env python3
"""
验证ETF日线接口获取昨收价
"""

import sys
sys.path.append('.')
from fetch_sector_data import _fetch_akshare_sina_etf

def verify_etf_daily_prev_close():
    """验证ETF日线接口获取昨收价"""
    print("=== 验证ETF日线接口获取昨收价 ===")

    # 测试几个ETF
    etf_codes = ['sh512480', 'sh511260', 'sh511130']

    for etf_code in etf_codes:
        print(f"\n--- {etf_code} ---")

        # 请求日线接口（2天数据）
        result = _fetch_akshare_sina_etf(etf_code, limit=2)

        if result and result.get('data') and len(result['data']) >= 2:
            yesterday = result['data'][-2]
            today = result['data'][-1]

            print(f"昨收价: {yesterday['close']}")
            print(f"今日收盘: {today['close']}")
            print(f"日线涨跌幅: {today['pct']}%")

            # 验证计算
            calc_pct = round((today['close'] - yesterday['close']) / yesterday['close'] * 100, 2)
            print(f"手动计算涨跌幅: {calc_pct}%")

            if calc_pct == today['pct']:
                print("✅ 计算正确")
            else:
                print("❌ 计算错误")

        else:
            print("❌ 接口失败")

if __name__ == "__main__":
    verify_etf_daily_prev_close()