#!/usr/bin/env python3
"""
国债ETF显示名称映射测试
"""

def test_bond_etf_mapping():
    """测试国债ETF名称映射"""
    print("=== 国债ETF显示名称映射测试 ===")

    # 国债ETF映射配置
    bond_mapping = {
        '511260': '十年国债',
        '511130': '三十年国债'
    }

    # 测试ETF数据
    etf_codes = ['511260', '511130', '512480', '516510']

    print("ETF代码映射结果:")
    for code in etf_codes:
        display_name = bond_mapping.get(code, code)  # 如果没有映射，显示原码
        print(f"{code} -> {display_name}")

    print("\n实际使用示例:")
    print("前端显示时：")
    print("- 511260 应显示为：十年国债")
    print("- 511130 应显示为：三十年国债")
    print("- 其他ETF保持原样：512480（半导体ETF）")

if __name__ == "__main__":
    test_bond_etf_mapping()