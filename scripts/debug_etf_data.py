#!/usr/bin/env python3
"""
调试ETF数据格式
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import akshare as ak

def _normalize_etf_code(code):
    """
    将6位ETF代码转换为带交易所前缀的格式
    """
    code_str = str(code).strip().replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
    if len(code_str) != 6 or not code_str.isdigit():
        return code_str
    first_digit = code_str[0]
    if first_digit == '5':
        return f"sh{code_str}"
    elif first_digit == '1':
        return f"sz{code_str}"
    else:
        return code_str

# 测试一个ETF
etf_code = "sh512480"
normalized = _normalize_etf_code(etf_code)

print(f"测试ETF: {etf_code}")
print(f"标准化后: {normalized}")
print()

# 获取数据
df = ak.fund_etf_hist_sina(symbol=normalized)

print(f"数据形状: {df.shape}")
print(f"列名: {list(df.columns)}")
print()
print("前5行数据:")
print(df.head())
print()
print("后5行数据:")
print(df.tail())
