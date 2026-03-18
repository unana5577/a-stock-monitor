#!/usr/bin/env python3
"""
测试数据源接口
"""
import json
import sys

def main():
    print("=" * 60)
    print("测试1: ETF成交额接口")
    print("=" * 60)
    try:
        import akshare as ak
        df = ak.fund_etf_category_sina(symbol="ETF基金")
        print("✅ 接口调用成功")
        print(f"数据行数: {len(df)}")
        print("\n列名:")
        print(df.columns.tolist())
        print("\n前5行数据:")
        print(df.head())

        if '成交额' in df.columns:
            total = float(df['成交额'].fillna(0).astype(float).sum())
            print(f"\n总成交额: {total:.0f}元 ({total/100000000:.2f}亿)")
            print(f"ETF数量: {len(df)}")
            etf_result = {
                "ok": True,
                "total_amount": total,
                "count": len(df),
                "total_yi": total / 100000000
            }
        else:
            print("\n❌ 未找到'成交额'列")
            etf_result = {"ok": False, "error": "missing column"}
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        etf_result = {"ok": False, "error": str(e)}

    print("\n" + "=" * 60)
    print("测试2: 涨跌家数接口")
    print("=" * 60)
    try:
        import akshare as ak
        df = ak.stock_board_industry_name_em()
        print("✅ 接口调用成功")
        print(f"数据行数: {len(df)}")
        print("\n列名:")
        print(df.columns.tolist())
        print("\n前5行数据:")
        print(df.head())

        if '上涨家数' in df.columns and '下跌家数' in df.columns:
            total_up = int(df['上涨家数'].sum())
            total_down = int(df['下跌家数'].sum())
            print(f"\n上涨家数: {total_up}")
            print(f"下跌家数: {total_down}")
            print(f"总家数: {total_up + total_down}")

            if total_down > 0:
                ratio = total_up / total_down
            else:
                ratio = float('inf')

            sentiment = '亢奋' if ratio > 2 else ('恐慌' if ratio < 0.3 else '正常')
            print(f"涨跌比: {ratio:.2f}")
            print(f"情绪: {sentiment}")

            breadth_result = {
                "ok": True,
                "up_count": total_up,
                "down_count": total_down,
                "total": total_up + total_down,
                "ratio": ratio,
                "sentiment": sentiment
            }
        else:
            print("\n❌ 未找到'上涨家数'或'下跌家数'列")
            breadth_result = {"ok": False, "error": "missing columns"}
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        breadth_result = {"ok": False, "error": str(e)}

    # 输出JSON结果
    print("\n" + "=" * 60)
    print("结果汇总")
    print("=" * 60)
    output = {
        "etf": etf_result,
        "breadth": breadth_result
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
