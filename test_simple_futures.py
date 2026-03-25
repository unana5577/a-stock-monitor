#!/usr/bin/env python3
"""
简单测试国债期货接口
只测试 T2606 和 TL2606
"""

import akshare as ak

def test_bond_futures():
    """测试国债期货接口"""
    print("=== 测试国债期货接口 ===")

    futures = ['T2606', 'TL2606']

    for code in futures:
        print(f"\n--- 测试 {code} ---")
        try:
            # 测试分钟数据
            df = ak.futures_zh_hist_min(symbol=code)
            if df is not None and not df.empty:
                print("✅ 分钟数据接口成功")
                print(f"最新价格: {df.iloc[-1]['收盘']}")
            else:
                print("❌ 分钟数据接口失败")

            # 测试日线数据
            df_daily = ak.futures_zh_hist_daily(symbol=code)
            if df_daily is not None and not df_daily.empty:
                print("✅ 日线数据接口成功")
                print(f"最新收盘: {df_daily.iloc[-1]['close']}")
            else:
                print("❌ 日线数据接口失败")

        except Exception as e:
            print(f"❌ 错误: {str(e)}")

if __name__ == "__main__":
    test_bond_futures()