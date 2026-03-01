import pandas as pd
from sector_lifecycle import calculate_alpha, calculate_amount_share, calculate_amount_share_ma5, determine_position, determine_stage, get_combo_info, analyze_sector, detect_false_kill


def test_calculate_alpha_positive():
    sector_return = 0.10
    market_return = 0.05
    result = calculate_alpha(sector_return, market_return)
    assert abs(result - 0.05) < 0.001


def test_calculate_alpha_negative():
    sector_return = 0.02
    market_return = 0.05
    result = calculate_alpha(sector_return, market_return)
    assert abs(result - (-0.03)) < 0.001


def test_calculate_alpha_zero_market():
    sector_return = 0.05
    market_return = 0.0
    result = calculate_alpha(sector_return, market_return)
    assert result == 0.05


def test_calculate_amount_share():
    sector_amount = 1000
    total_amount = 5000
    result = calculate_amount_share(sector_amount, total_amount)
    assert abs(result - 0.2) < 0.001


def test_calculate_amount_share_ma5():
    history = [0.1, 0.15, 0.2, 0.18, 0.2]
    result = calculate_amount_share_ma5(history)
    assert abs(result - 0.166) < 0.01


def test_determine_position_overheated():
    result = determine_position(alpha_20=0.10, amount_share_ma5=0.6)
    assert result["区域"] == "高位区"
    assert result["位置"] == "过热期"


def test_determine_position_strong():
    result = determine_position(alpha_20=0.10, amount_share_ma5=0.4)
    assert result["区域"] == "高位区"
    assert result["位置"] == "强势期"


def test_determine_position_active():
    result = determine_position(alpha_20=0.05, amount_share_ma5=0.4)
    assert result["区域"] == "中位区"
    assert result["位置"] == "活跃期"


def test_determine_position_neutral():
    result = determine_position(alpha_20=0.0, amount_share_ma5=0.4)
    assert result["区域"] == "中位区"
    assert result["位置"] == "中性期"


def test_determine_position_frozen():
    result = determine_position(alpha_20=-0.05, amount_share_ma5=0.2)
    assert result["区域"] == "低位区"
    assert result["位置"] == "冰点期"


def test_determine_stage_recession():
    result = determine_stage(
        close=3000,
        ma20=3100,
        ma60=3200,
        bias_20=-3.2,
        pct=-2.5,
        amount_share=0.4,
        rs_change_20=0.1
    )
    assert result == "衰退期"


def test_determine_stage_launch():
    result = determine_stage(
        close=3300,
        ma20=3200,
        ma60=3100,
        ma60_slope=0.01,
        bias_20=3.5,
        pct=2.5,
        amount_share=0.65,
        rs_change_20=0.2
    )
    assert result == "启动期"


def test_determine_stage_acceleration():
    result = determine_stage(
        close=3400,
        ma20=3200,
        ma60=3100,
        ma20_slope=0.02,
        bias_20=8.5,
        pct=3.0,
        amount_share=0.5,
        rs_change_20=0.3
    )
    assert result == "加速期"


def test_determine_stage_oscillation():
    result = determine_stage(
        close=3250,
        ma20=3200,
        ma60=3100,
        ma20_slope=0.1,
        bias_20=3.5,
        pct=0.5,
        amount_share=0.4,
        rs_change_20=0.1
    )
    assert result == "震荡期"


def test_determine_stage_dormant():
    result = determine_stage(
        close=3000,
        ma20=2900,
        ma60=3100,
        bias_20=-3.2,
        pct=-0.5,
        amount_share=0.2,
        rs_change_20=-0.1
    )
    assert result == "潜伏期"


def test_get_display_name():
    result = get_combo_info("过热期", "加速期")
    assert result["显示名称"] == "过热·加速赶顶"
    assert result["操作建议"] == "分批止盈"


def test_get_display_name_default():
    result = get_combo_info("未知", "未知")
    assert result["显示名称"] == "待观察"


def test_detect_false_kill_by_down_total_ratio():
    result = detect_false_kill(
        sector_data={"alpha_20": 0.02, "amount_share": 0.3, "amount_share_p80": 0.4},
        market_breadth={"up": 1200, "down": 2500, "total": 3700, "market_return": -0.3},
        news_factor=None
    )
    assert result is True


def test_detect_false_kill_not_triggered_when_ratio_below_threshold():
    result = detect_false_kill(
        sector_data={"alpha_20": 0.02, "amount_share": 0.3, "amount_share_p80": 0.4},
        market_breadth={"up": 1500, "down": 2000, "total": 4000, "market_return": -0.3},
        news_factor=None
    )
    assert result is False


def test_analyze_sector_full():
    sector_data = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=60, freq="D"),
        "close": [3000 + i * 5 for i in range(60)],
        "amount": [1000 + i * 10 for i in range(60)]
    })
    market_data = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=60, freq="D"),
        "close": [3000 + i * 3 for i in range(60)],
        "amount": [20000 + i * 50 for i in range(60)]
    })
    result = analyze_sector(sector_data, market_data, "半导体", "上证", 0.8, market_data, sector_data)
    assert "板块名称" in result
    assert "基准指数" in result
    assert "相关性" in result
    assert "板块位置" in result
    assert "动能" in result
    assert "资金行为" in result
    assert "位置区域" in result
    assert "阶段信号" in result
    assert "显示名称" in result
    assert "操作建议" in result
    assert "归因说明" in result
    assert "乖离对比" in result
