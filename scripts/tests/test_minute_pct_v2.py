#!/usr/bin/env python3
"""
分时数据涨跌幅计算测试脚本（增强版）
"""

import json
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_sector_minute_directly():
    """直接测试东财板块分时接口"""
    print("\n=== 直接测试东财板块分时接口 ===")
    try:
        import akshare as ak

        # 获取银行板块分钟数据
        df = ak.stock_zh_a_hist_min_em(symbol="sh000001", period='1', adjust='')
        print("东财接口调用成功")
        print("数据列:", df.columns.tolist())
        print("数据形状:", df.shape)

        if not df.empty:
            print("前5行:")
            print(df.head())

            # 获取今日数据
            today = datetime.now().strftime('%Y-%m-%d')
            filtered = df[df['时间'].astype(str).str.startswith(today)]
            print(f"\n今日数据条数: {len(filtered)}")

            if len(filtered) > 0:
                print("今日前3行:")
                for i, row in filtered.head(3).iterrows():
                    print(f"时间: {row['时间']}, 开盘: {row['开盘']}, 收盘: {row['收盘']}")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")

def test_etf_minute_directly():
    """直接测试ETF分时接口"""
    print("\n=== 直接测试ETF分时接口 ===")
    try:
        import akshare as ak

        # 获取ETF分钟数据
        df = ak.fund_etf_hist_min_em(symbol="512480", period='1', adjust='')
        print("ETF接口调用成功")
        print("数据列:", df.columns.tolist())
        print("数据形状:", df.shape)

        if not df.empty:
            print("前5行:")
            print(df.head())

            # 获取今日数据
            today = datetime.now().strftime('%Y-%m-%d')
            filtered = df[df['时间'].astype(str).str.startswith(today)]
            print(f"\n今日数据条数: {len(filtered)}")

            if len(filtered) > 0:
                print("今日前3行:")
                for i, row in filtered.head(3).iterrows():
                    print(f"时间: {row['时间']}, 价格: {row['收盘']}")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")

def test_snapshot_interface():
    """测试快照接口"""
    print("\n=== 测试快照接口（获取昨收）===")
    try:
        import akshare as ak

        # 获取A股快照
        df = ak.stock_zh_a_spot_em()
        print("快照接口调用成功")
        print("数据列:", df.columns.tolist())
        print("数据形状:", df.shape)

        # 查找上证指数
        index_data = df[df['代码'] == '000001']
        if not index_data.empty:
            row = index_data.iloc[0]
            print(f"上证指数: {row['名称']}, 最新价: {row['最新价']}, 涨跌幅: {row['涨跌幅']}")

    except Exception as e:
        print(f"❌ 错误: {str(e)}")

if __name__ == "__main__":
    print("开始测试分时数据接口...\n")

    test_sector_minute_directly()
    test_etf_minute_directly()
    test_snapshot_interface()

    print("\n测试完成！")