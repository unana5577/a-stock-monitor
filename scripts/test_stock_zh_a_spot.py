#!/usr/bin/env python3
"""
测试A股实时行情接口 stock_zh_a_spot()
用于获取全市场涨跌家数统计
"""
import json
import sys

def main():
    print("=" * 60)
    print("测试: A股实时行情接口 - stock_zh_a_spot()")
    print("=" * 60)
    try:
        import akshare as ak
        print("正在获取数据...")
        df = ak.stock_zh_a_spot()
        print("✅ 接口调用成功")
        print(f"数据行数: {len(df)}")
        print("\n列名:")
        print(df.columns.tolist())
        print("\n前10行数据:")
        print(df.head(10))

        # 统计涨跌家数
        if '涨跌幅' in df.columns:
            up = df[df['涨跌幅'] > 0].shape[0]
            down = df[df['涨跌幅'] < 0].shape[0]
            flat = df[df['涨跌幅'] == 0].shape[0]

            total = up + down + flat
            ratio = up / down if down > 0 else float('inf')

            # 情绪判断
            if ratio < 0.3:
                sentiment = "恐慌"
            elif ratio > 2.0:
                sentiment = "亢奋"
            else:
                sentiment = "正常"

            print("\n" + "=" * 60)
            print("涨跌家数统计")
            print("=" * 60)
            print(f"上涨: {up}")
            print(f"下跌: {down}")
            print(f"平盘: {flat}")
            print(f"总计: {total}")
            print(f"涨跌比: {ratio:.2f}")
            print(f"市场情绪: {sentiment}")

            result = {
                "ok": True,
                "up": up,
                "down": down,
                "flat": flat,
                "total": total,
                "ratio": round(ratio, 2),
                "sentiment": sentiment
            }
        else:
            print("\n❌ 未找到'涨跌幅'列")
            result = {"ok": False, "error": "missing column"}

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        result = {"ok": False, "error": str(e)}

    print("\n" + "=" * 60)
    print("结果")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
