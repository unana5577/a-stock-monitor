#!/usr/bin/env python3
"""
sector_lifecycle - 板块生命周期分析模块

提供ETF操作建���的完整分析流程：
1. 数据加载
2. 动态基准选择
3. 指标计算（Alpha、趋势、量能、乖离率）
4. 操作建议生成
"""

from .data_loader import DataLoader
from .benchmark import BenchmarkSelector
from .indicators import Indicators
from .advice import AdviceGenerator

__all__ = [
    'DataLoader',
    'BenchmarkSelector',
    'Indicators',
    'AdviceGenerator',
]
