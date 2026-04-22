#!/usr/bin/env python3
"""
操作建议生成模块

功能：
- 根据风险等级、资金热度、趋势生成操作建议
- 完整映射表（17种场景）
"""

from typing import Tuple


class AdviceGenerator:
    """操作建议生成器"""

    @staticmethod
    def generate_advice(risk_level: str, fund_status: str, ma5_slope: float) -> Tuple[str, str]:
        """生成操作建议（与完整映射表保持一致）

        Args:
            risk_level: 风险等级
            fund_status: 资金热度（放量/缩量/持平）
            ma5_slope: MA5斜率

        Returns:
            (操作建议, 原因)
        """

        is_up = ma5_slope > 0

        # 极度风险/高风险 → 减仓/离场
        if risk_level == "极度风险":
            return "减仓/离场", "乖离率过高，注意回调风险"
        elif risk_level == "高风险":
            return "逐步减仓", "锁定利润，防范回调"

        # 极度超跌
        elif risk_level == "极度超跌":
            if fund_status == "放量":
                return "关注企稳/抄底", "超跌+资金进场，关注反弹"
            else:
                return "等待放量", "等待底部信号"

        # 低风险
        elif risk_level == "低风险":
            if fund_status == "放量" and is_up:
                return "关注企稳/试水", "低位+资金进场，关注机会"
            elif fund_status == "放量" and not is_up:
                return "关注企稳", "关注企稳信号"
            else:
                return "继续观察", "等待资金进场"

        # 中低位风险
        elif risk_level == "中低位风险":
            if fund_status == "放量" and is_up:
                return "小仓位试水", "风险较低+资金进场"
            elif fund_status == "放量" and not is_up:
                return "关注", "关注企稳机会"
            elif fund_status == "缩量" and is_up:
                return "继续观察", "等待放量确认"
            else:
                return "继续观察", "等待企稳信号"

        # 中位风险
        elif risk_level == "中位风险":
            if fund_status == "放量" and is_up:
                return "小仓位试水", "趋势向上+资金确认"
            elif fund_status == "放量" and not is_up:
                return "观望", "等待方向明确"
            else:  # 缩量
                return "观望", "缩量震荡，等待突破"

        # 中高位风险
        elif risk_level == "中高位风险":
            if fund_status == "放量" and is_up:
                return "小仓位试水", "风险适中+资金进场"
            elif fund_status == "放量" and not is_up:
                return "观望", "等待企稳信号"
            else:  # 缩量
                return "观望", "缺乏资金支持"

        # 其他
        else:
            return "观望", "等待信号"

    @staticmethod
    def generate_action_with_risk(
        risk_level: str,
        momentum: str,
        fund_behavior: str
    ) -> Tuple[str, str]:
        """生成操作建议（含仓位指导，三维决策模型）

        基于sector_lifecycle.py的逻辑，加入风险管理维度

        Args:
            risk_level: 风险等级（乖离率）
            momentum: 动能标签
            fund_behavior: 资金行为标签

        Returns:
            (操作建议, 仓位指导说明)
        """

        # 极度风险/高风险 → 判断是否有主线逼空溢价
        if risk_level in ["极度风险", "高风险"]:
            if momentum == "强势向上" and fund_behavior == "加速赶顶": # 原逻辑在突破后可能会将持续加速判为赶顶，这里兼容处理
                # 如果是明确传入的主线逼空，由上层逻辑保证，或者在这里增加更精细的判断
                pass
            if momentum == "强势向上" and (fund_behavior == "主线逼空(连续新高)" or fund_behavior == "加速赶顶"):
                # 这里为了兼容，实际如果连续新高在外面被判定为“加速赶顶”，前端也可以拦截。
                # 但如果在后端加，最好有个标志位。这里我们按文档要求补充这个条件
                if fund_behavior == "主线逼空(连续新高)":
                    return "主线持有", "突破极值且连续强势，主线确立，格局持有"
                else:
                    return "逐步减仓", "高风险，锁定利润，减仓至半仓以下"
            elif risk_level == "极度风险":
                return "减仓/离场", "极度风险，乖离率过高，清仓离场"
            else:
                return "逐步减仓", "高风险，锁定利润，减仓至半仓以下"

        # 极度超跌
        elif risk_level == "极度超跌":
            if momentum == "弱势反弹" and fund_behavior == "放量启动":
                return "关注企稳", "极度超跌+弱势反弹+放量启动，轻仓试探"
            else:
                return "等待放量", "极度超跌，等待底部信号，空仓观望"

        # 中低位风险
        elif risk_level == "中低位风险":
            if momentum == "强势向上" and fund_behavior == "放量启动":
                return "积极建仓", "中低位风险+强势向上+放量启动，半仓以上"
            elif momentum == "偏强向上" and fund_behavior == "放量启���":
                return "轻仓试探", "中低位风险+偏强向上+放量启动，轻仓20%"
            elif momentum == "中性震荡" and fund_behavior == "放量启动":
                return "小仓埋伏", "中低位风险+中性震荡+放量启动，小仓10%"
            else:
                return "观望", "中低位风险，等待更明确信号"

        # 中位风险
        elif risk_level == "中位风险":
            if momentum == "强势向上" and fund_behavior == "放量启动":
                return "持股待涨", "中位风险+强势向上+放量启动，持有或重仓"
            elif momentum == "偏强向上" and fund_behavior == "横盘整理":
                return "持有", "中位风险+偏强向上+横盘整理，持有"
            elif fund_behavior == "资金撤退":
                return "逐步减仓", "中位风险+资金撤退，减仓"
            else:
                return "观望", "中位风险，等待确认信号"

        # 中高位风险
        elif risk_level == "中高位风险":
            if momentum == "强势向上" and fund_behavior == "加速赶顶":
                return "分批止盈", "中高位风险+强势向上+加速赶顶，分批止盈"
            elif momentum == "强势向上" and fund_behavior == "主线逼空(连续新高)":
                return "主线持有", "突破极值且连续强势，主线确立，格局持有"
            elif momentum == "弱势向下" and fund_behavior == "恐慌出逃":
                return "果断止损", "中高位风险+弱势向下+恐慌出逃，立即清仓"
            else:
                return "观望", "中高位风险，谨慎操作"

        # 低风险
        elif risk_level == "低风险":
            if momentum == "弱势向下" and fund_behavior == "资金撤退":
                return "空仓观望", "低风险+弱势向下+资金撤退，空仓观望"
            elif momentum == "弱势反弹" and fund_behavior == "超跌反弹":
                return "关注企稳", "低风险+弱势反弹+超跌反弹，观察等待"
            else:
                return "观望等待", "低风险，等待确认信号"

        # 其他
        else:
            return "观望等待", "等待信号"
