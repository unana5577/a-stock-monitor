#!/usr/bin/env python3
"""
测试东财期货接口能否获取国债期货数据
- T2606: 10年期国债期货（2026年6月合约）
- TL2606: 30年期国债期货（2026年6月合约）
"""

import akshare as ak
import sys

def test_futures_interface():
    """测试东财期货接口"""
    print("=== 测试东财国债期货接口 ===")

    # 期货代码映射
    futures_codes = {
        'T2606': '10年期国债期货（2026年6月）',
        'TL2606': '30年期国债期货（2026年6月）'
    }

    for code, desc in futures_codes.items():
        print(f"\n--- 测试 {code} ({desc}) ---")
        try:
            # 尝试获取期货分钟数据
            df = ak.futures_zh_hist_min(symbol=code)

            if df is not None and not df.empty:
                print("✅ 接口调用成功")
                print(f"数据列: {df.columns.tolist()}")
                print(f"数据形状: {df.shape}")

                # 显示最近的数据
                if len(df) > 0:
                    print("\n最近3条数据:")
                    for i, row in df.head(3).iterrows():
                        print(f"时间: {row['时间']}, 开盘: {row['开盘']}, 收盘: {row['收盘']}, 最高: {row['最高']}, 最低: {row['最低']}")

                # 尝试获取日线数据
                df_daily = ak.futures_zh_hist_daily(symbol=code)
                if df_daily is not None and not df_daily.empty:
                    print("\n日线数据（最近3条）:")
                    for i, row in df_daily.head(3).iterrows():
                        print(f"日期: {row['date']}, 开盘: {row['open']}, 收盘: {row['close']}, 涨跌: {row['change']}")

            else:
                print("❌ 接口返回空数据")

        except Exception as e:
            print(f"❌ 错误: {str(e)}")

def test_stock_futures_interface():
    """测试股指期货接口（如沪深300期货）"""
    print("\n=== 测试股指期货接口 ===")

    stock_futures_codes = {
        'IF2606': '沪深300指数期货（2026年6月）',
        'IH2606': '上证50指数期货（2026年6月）',
        'IC2606': '中证500指数期货（2026年6月）'
    }

    for code, desc in stock_futures_codes.items():
        print(f"\n--- 测试 {code} ({desc}) ---")
        try:
            df = ak.futures_zh_hist_min(symbol=code)

            if df is not None and not df.empty:
                print("✅ 接口调用成功")
                print(f"数据列: {df.columns.tolist()}")
                print(f"数据形状: {df.shape}")

                # 显示最近的数据
                if len(df) > 0:
                    print("\n最近3条数据:")
                    for i, row in df.head(3).iterrows():
                        print(f"时间: {row['时间']}, 开盘: {row['开盘']}, 收盘: {row['收盘']}")

            else:
                print("❌ 接口返回空数据")

        except Exception as e:
            print(f"❌ 错误: {str(e)}")

def test_futures_main_contract():
    """测试主力合约接口"""
    print("\n=== 测试主力合约接口 ===")

    try:
        # 获取国债期货主力合约
        df_main = ak.futures_main_sina()
        print("国债期货主力合约:")
        print(df_main)

        # 获取股指期货主力合约
        df_index_main = ak.futures_zh_spot()
        print("\n股指期货主力合约:")
        print(df_index_main)

    except Exception as e:
        print(f"❌ 错误: {str(e)}")

if __name__ == "__main__":
    print("开始测试东财期货接口...\n")

    test_futures_interface()
    test_stock_futures_interface()
    test_futures_main_contract()

    print("\n测试完成！")