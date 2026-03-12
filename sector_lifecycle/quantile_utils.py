"""
分位数计算工具

用于计算指标的历史分位数，支持动态阈值优化
"""
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np


def calculate_rolling_quantile(
    series: pd.Series,
    window: int = 60,
    quantiles: List[float] = [0.2, 0.4, 0.6, 0.8]
) -> Dict[float, pd.Series]:
    """
    计算滚动分位数

    Args:
        series: 指标序列（必须是 pd.Series）
        window: 滚动窗口大小（交易日）
        quantiles: 要计算的分位数列表，如 [0.2, 0.4, 0.6, 0.8]

    Returns:
        字典，键为分位数值，值为对应的分位数序列

    Example:
        >>> series = pd.Series([1, 2, 3, 4, 5])
        >>> result = calculate_rolling_quantile(series, window=3)
        >>> result[0.8]  # 80%分位数序列
    """
    if len(series) < window:
        # 数据不足时，用全部数据计算
        rolling = series.expanding()
    else:
        rolling = series.rolling(window=window, min_periods=1)

    result = {}
    for q in quantiles:
        result[q] = rolling.quantile(q)

    return result


def get_current_quantile_position(
    current_value: float,
    historical_series: pd.Series
) -> float:
    """
    计算当前值在历史序列中的分位位置

    Args:
        current_value: 当前值
        historical_series: 历史序列

    Returns:
        分位位置（0-1之间），如 0.85 表示超过85%的历史时期

    Example:
        >>> history = pd.Series([1, 2, 3, 4, 5])
        >>> get_current_quantile_position(4.5, history)
        0.8
    """
    if len(historical_series) == 0:
        return 0.5

    # 计算有多少历史值小于当前值
    less_count = (historical_series < current_value).sum()
    total_count = len(historical_series)

    if total_count == 0:
        return 0.5

    return less_count / total_count


def calculate_multiple_indicators_quantiles(
    df: pd.DataFrame,
    indicators: List[str],
    window: int = 60,
    quantiles: List[float] = [0.2, 0.4, 0.6, 0.8]
) -> Dict[str, Dict[float, float]]:
    """
    批量计算多个指标的当前分位数

    Args:
        df: 包含多列的数据框
        indicators: 要计算的指标列名列表
        window: 滚动窗口大小
        quantiles: 要计算的分位数列表

    Returns:
        嵌套字典，格式为 {指标名: {分位数: 当前值}}
        例如: {"Alpha_20": {0.8: 0.05, 0.6: 0.03}}

    Example:
        >>> df = pd.DataFrame({
        ...     "Alpha_20": [0.01, 0.02, 0.03, 0.04, 0.05],
        ...     "Amount_Share": [0.02, 0.03, 0.04, 0.05, 0.06]
        ... })
        >>> result = calculate_multiple_indicators_quantiles(
        ...     df,
        ...     indicators=["Alpha_20", "Amount_Share"],
        ...     window=3
        ... )
        >>> result["Alpha_20"][0.8]  # Alpha_20的80%分位数当前值
    """
    result = {}

    for indicator in indicators:
        if indicator not in df.columns:
            continue

        series = df[indicator].dropna()
        if len(series) == 0:
            continue

        # 计算滚动分位数
        rolling_quantiles = calculate_rolling_quantile(series, window, quantiles)

        # 获取每个分位数的最新值
        result[indicator] = {}
        for q in quantiles:
            q_series = rolling_quantiles.get(q)
            if q_series is not None and len(q_series) > 0:
                result[indicator][q] = float(q_series.iloc[-1])

    return result


def find_optimal_thresholds_by_accuracy(
    true_values: List[float],
    predicted_labels: List[str],
    label_map: Dict[str, int],
    thresholds_range: Tuple[float, float] = (0.5, 0.95),
    step: float = 0.05
) -> Dict[str, float]:
    """
    通过网格搜索寻找最优阈值（基于准确率）

    Args:
        true_values: 真实值序列（如涨跌幅）
        predicted_labels: 预测标签序列
        label_map: 标签到数值的映射，如 {"看涨": 1, "看跌": -1}
        thresholds_range: 阈值搜索范围
        step: 搜索步长

    Returns:
        最优阈值配置，格式为 {指标名: 最优阈值}
    """
    # TODO: 在阈值优化器中实现
    pass


def validate_threshold_config(
    config: Dict[str, Dict[str, float]],
    available_indicators: List[str]
) -> bool:
    """
    验证阈值配置的合法性

    Args:
        config: 阈值配置字典
        available_indicators: 可用的指标列表

    Returns:
        是否合法
    """
    if not isinstance(config, dict):
        return False

    for indicator, thresholds in config.items():
        if indicator not in available_indicators:
            print(f"警告: 指标 '{indicator}' 不在可用指标列表中")
            return False

        if not isinstance(thresholds, dict):
            return False

        # 检查阈值是否在合理范围内
        for key, value in thresholds.items():
            try:
                q = float(key)
                if not (0 <= q <= 1):
                    print(f"警告: 分位数 '{q}' 不在 [0, 1] 范围内")
                    return False
            except ValueError:
                print(f"警告: 阈值键 '{key}' 不是有效的分位数")
                return False

    return True


def merge_threshold_configs(
    base_config: Dict[str, Dict[str, float]],
    override_config: Dict[str, Dict[str, float]]
) -> Dict[str, Dict[str, float]]:
    """
    合并阈值配置（override_config 覆盖 base_config）

    Args:
        base_config: 基础配置
        override_config: 覆盖配置

    Returns:
        合并后的配置
    """
    result = base_config.copy()

    for indicator, thresholds in override_config.items():
        if indicator not in result:
            result[indicator] = {}
        result[indicator].update(thresholds)

    return result
