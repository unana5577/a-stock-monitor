# -*- coding: utf-8 -*-
"""
测试脚本 - 验证核心模块是否正常工作
"""

import sys
import os

# 添加 backend 目录到 Python 路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

print("=" * 60)
print("测试核心模块")
print("=" * 60)

# 测试 1: 导入配置模块
print("\n1️⃣ 测试导入 sector_lifecycle_config...")
try:
    from sector_lifecycle_config import (
        ALPHA_THRESHOLDS,
        SECTORS,
        get_position_zone,
        get_combo_info
    )
    print("  ✅ 导入成功")
    print(f"  📊 板块列表: {SECTORS}")
    print(f"  📈 Alpha 阈值: {ALPHA_THRESHOLDS}")
except Exception as e:
    print(f"  ❌ 导入失败: {e}")
    sys.exit(1)

# 测试 2: 导入核心逻辑模块
print("\n2️⃣ 测试导入 sector_lifecycle...")
try:
    from sector_lifecycle import (
        calculate_alpha,
        calculate_alpha_n,
        calculate_amount_share,
        determine_position,
        determine_stage,
        analyze_sector
    )
    print("  ✅ 导入成功")
except Exception as e:
    print(f"  ❌ 导入失败: {e}")
    sys.exit(1)

# 测试 3: 测试位置判断
print("\n3️⃣ 测试位置判断...")
try:
    zone, name = determine_position(0.10, 0.45)
    print(f"  Alpha_20=10%, Amount_Share=45% → {zone}, {name}")
    
    zone, name = determine_position(-0.05, 0.10)
    print(f"  Alpha_20=-5%, Amount_Share=10% → {zone}, {name}")
    
    print("  ✅ 位置判断正常")
except Exception as e:
    print(f"  ❌ 测试失败: {e}")
    sys.exit(1)

# 测试 4: 测试组合信息
print("\n4️⃣ 测试组合信息...")
try:
    display, meaning, advice, risk = get_combo_info("过热期", "加速期")
    print(f"  过热期 + 加速期:")
    print(f"    显示名称: {display}")
    print(f"    含义: {meaning}")
    print(f"    建议: {advice}")
    print(f"    风险: {risk}")
    print("  ✅ 组合信息正常")
except Exception as e:
    print(f"  ❌ 测试失败: {e}")
    sys.exit(1)

# 测试 5: 测试数据获取模块
print("\n5️⃣ 测试导入 fetch_sector_data...")
try:
    from fetch_sector_data import (
        fetch_sector_hist,
        fetch_index_hist,
        fetch_market_breadth,
        SECTORS as FETCH_SECTORS
    )
    print("  ✅ 导入成功")
    print(f"  📊 板块列表: {FETCH_SECTORS}")
except Exception as e:
    print(f"  ❌ 导入失败: {e}")
    sys.exit(1)

# 测试 6: 测试回测模块
print("\n6️⃣ 测试导入 backtest_thresholds...")
try:
    from backtest_thresholds import (
        validate_prediction,
        backtest_sector,
        calculate_metrics
    )
    print("  ✅ 导入成功")
    
    # 测试验证函数
    is_correct = validate_prediction("持有待涨", 5.0)
    print(f"  建议'持有待涨', 未来收益 5% → 正确: {is_correct}")
    
    is_correct = validate_prediction("果断清仓", -3.0)
    print(f"  建议'果断清仓', 未来收益 -3% → 正确: {is_correct}")
    
    print("  ✅ 验证函数正常")
except Exception as e:
    print(f"  ❌ 导入失败: {e}")
    sys.exit(1)

# 测试 7: 完整分析测试
print("\n7️⃣ 测试完整分析...")
try:
    import pandas as pd
    import numpy as np
    
    # 生成测试数据
    dates = pd.date_range("2025-01-01", periods=100, freq="D")
    
    sector_df = pd.DataFrame({
        "date": dates,
        "close": np.cumsum(np.random.randn(100) * 10 + 100),
        "pct": np.random.randn(100) * 2,
        "amount": np.random.rand(100) * 1e9 + 1e8
    })
    
    market_df = pd.DataFrame({
        "date": dates,
        "close": np.cumsum(np.random.randn(100) * 5 + 3000),
        "pct": np.random.randn(100) * 1,
        "amount": np.random.rand(100) * 1e10 + 1e9
    })
    
    result = analyze_sector(sector_df, market_df, "测试板块")
    
    print(f"  板块: {result['sector']}")
    print(f"  位置: {result['position_zone']} - {result['position_name']}")
    print(f"  阶段: {result['stage_signal']}")
    print(f"  显示: {result['display_name']}")
    print(f"  建议: {result['advice']}")
    print(f"  Alpha_20: {result['alpha_20']}%")
    print(f"  成交额占比: {result['amount_share']}%")
    
    print("  ✅ 完整分析正常")
except Exception as e:
    print(f"  ❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 总结
print("\n" + "=" * 60)
print("✅ 所有测试通过！")
print("=" * 60)
print("\n📝 核心模块状态:")
print("  ✅ sector_lifecycle_config.py - 配置模块")
print("  ✅ sector_lifecycle.py - 核心逻辑模块")
print("  ✅ fetch_sector_data.py - 数据获取模块")
print("  ✅ backtest_thresholds.py - 回测模块")
print("\n🚀 可以开始使用了！")
print("\n💡 使用方法:")
print("  1. 运行回测: python backtest_thresholds.py")
print("  2. 获取数据: python fetch_sector_data.py")
print("  3. 查看配置: python sector_lifecycle_config.py")
