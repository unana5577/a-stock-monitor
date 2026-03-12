#!/usr/bin/env python3
"""
ETF数据源验证脚本

⚠️ CRITICAL: 此脚本验证ETF数据源配置是否正确
- 运行时机：每次修改ETF配置后必须运行
- 验证内容：代码格式���数据可用性、起始日期要求
- 失败处理：如有失败，禁止部署到生产环境

使用方法：
  python3 scripts/verify_etf_datasource.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_sector_data import _load_proxy_mapping, _proxy_history_payload
from datetime import datetime

def verify_etf_code_format(code):
    """
    验证ETF代码格式
    要求：6位数字 + sh/sz前缀
    """
    # 检查是否有前缀
    if not (code.startswith('sh') or code.startswith('sz')):
        return False, f"❌ 缺少交易所前缀: {code}"

    # 提取纯数字部��
    clean_code = code.replace('sh', '').replace('sz', '')

    # 检查是否为6位数字
    if len(clean_code) != 6 or not clean_code.isdigit():
        return False, f"❌ 代码格式错误: {code}"

    # 检查交易所规则
    first_digit = clean_code[0]
    if first_digit == '5':
        return True, f"✅ 上交所ETF: {code}"
    elif first_digit == '1':
        return True, f"✅ 深交所ETF: {code}"
    else:
        return False, f"❌ 无效的交易所代码: {code}"

def verify_etf_data(code, sector_name):
    """
    验证ETF数据是否满足要求
    要求：
    1. 数据存在
    2. 起始日期 <= 2025-05-19
    3. 数据量 >= 300天
    """
    try:
        from fetch_sector_data import _fetch_tencent_daily

        result = _fetch_tencent_daily(code, limit=365)

        if not result.get("data"):
            return False, f"❌ 无数据: {code}"

        data = result["data"]
        start_date = data[0]['date']
        end_date = data[-1]['date']
        count = len(data)

        # 检查起始日期
        if start_date > "2025-05-19":
            return False, f"❌ 起始日期不满足要求: {start_date} > 2025-05-19"

        # 检查数据量
        if count < 300:
            return False, f"❌ 数据量不足: {count}天 < 300天"

        return True, f"✅ 数据验证通过: {start_date} 至 {end_date}, {count}天"
    except Exception as e:
        return False, f"❌ 数据获取失败: {str(e)}"

def main():
    print("=" * 80)
    print("ETF数据源验证")
    print("=" * 80)
    print(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 加载proxy配置
    cfg = _load_proxy_mapping()
    etf_map = (cfg.get('variants') or {}).get('etf') or {}

    if not etf_map:
        print("❌ 未找到ETF配置")
        return False

    print(f"验证板块数: {len(etf_map)}")
    print()

    # 验证每个ETF
    all_passed = True
    for sector, code in etf_map.items():
        print(f"{'='*80}")
        print(f"板块: {sector}")
        print(f"代码: {code}")
        print(f"{'-'*80}")

        # 验证代码格式
        format_ok, format_msg = verify_etf_code_format(code)
        print(f"格式验证: {format_msg}")
        if not format_ok:
            all_passed = False
            continue

        # 验证数据
        data_ok, data_msg = verify_etf_data(code, sector)
        print(f"数据验证: {data_msg}")
        if not data_ok:
            all_passed = False
            continue

        print(f"✅ {sector} 验证通过")
        print()

    # 最终汇总
    print("=" * 80)
    print("验证结果汇总")
    print("=" * 80)

    if all_passed:
        print("✅ 所有ETF验证通过")
        print()
        print("数据源配置:")
        print("  - 接口: AkShare Sina fund_etf_hist_sina()")
        print("  - 位置: fetch_sector_data.py:_fetch_akshare_sina_etf()")
        print("  - 检测: _fetch_tencent_daily()自动识别ETF代码")
        print("  - 状态: 可用于生产环境")
        return True
    else:
        print("❌ 部分ETF验证失败")
        print()
        print("⚠️  请修复错误后再部署到生产环境")
        print("⚠️  常见问题:")
        print("   1. ETF代码缺少sh/sz前缀")
        print("   2. ETF代码不存在或已退市")
        print("   3. 数据源接口异常")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
