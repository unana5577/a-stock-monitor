#!/usr/bin/env python3
"""
测试各接口返回数据，确认pct计算方案
"""

def test_large_cap_minute():
    """测试大盘指数分时接口"""
    print("=== 测试大盘指数分时接口 ===")

    import sys
    sys.path.append('.')
    from fetch_sector_data import _fetch_ashare_minute

    result = _fetch_ashare_minute('sh000001', count=5)
    print(f"返回数据: {result}")
    print(f"prevClose: {result.get('prevClose')}")
    print(f"数据条数: {len(result.get('data', []))}")

def test_sector_api():
    """测试板块接口"""
    print("\n=== 测试板块接口 ak.stock_board_industry_name_em ===")

    try:
        import akshare as ak
        df = ak.stock_board_industry_name_em()
        print("接口调用成功")
        print(f"数据形状: {df.shape}")
        print(f"数据列: {df.columns.tolist()}")
        print("\n前5行数据:")
        print(df.head())
    except Exception as e:
        print(f"错误: {e}")

def test_bond_etf_daily():
    """测试国债ETF日线接口"""
    print("\n=== 测试国债ETF日线接口 ===")

    try:
        import akshare as ak
        import sys
        sys.path.append('.')
        from fetch_sector_data import _fetch_akshare_sina_etf

        # 测试511260（十年国债）
        print("测试511260（十年国债）:")
        result = _fetch_akshare_sina_etf('sh511260', limit=5)
        if result.get('data'):
            print(f"✅ 接口成功，返回 {len(result['data'])} 条数据")
            print(f"最新数据: {result['data'][-1]}")
        else:
            print("❌ 接口失败")

    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    test_large_cap_minute()
    test_sector_api()
    test_bond_etf_daily()