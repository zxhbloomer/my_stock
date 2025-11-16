"""
中国A股市场特色因子库
针对A股市场特点设计的14个定制因子

因子分类：
1. 涨跌停板因子（5个）：A股特有的±9.5%涨跌停限制
2. 量价配合因子（4个）：成交量与价格变化的协同关系
3. 动量反转因子（3个）：短期动量与长期反转效应
4. 行业轮动因子（2个）：行业相对强度与轮动信号

作者：Claude Code
日期：2025-11-15
"""


class ChinaMarketFactors:
    """中国A股特色因子集合"""

    @staticmethod
    def get_limit_factors():
        """
        涨跌停板因子（5个）

        A股特色：
        - 涨跌停板限制±9.5%（ST股±5%）
        - 涨停后次日行为模式
        - 连续涨停的强势信号

        Returns:
            list: 5个涨跌停相关因子表达式
        """
        return [
            # 因子1: 是否涨停（接近或达到9.5%）
            "If($close / Ref($close, 1) - 1 >= 0.095, 1, 0)",

            # 因子2: 是否跌停（接近或达到-9.5%）
            "If($close / Ref($close, 1) - 1 <= -0.095, 1, 0)",

            # 因子3: 5日内涨停次数（强势股标志）
            "Sum(If($close / Ref($close, 1) - 1 >= 0.095, 1, 0), 5)",

            # 因子4: 连续涨停天数（极强势信号）
            # 近似实现：检查过去3天是否连续涨停
            "If("
            "    ($close / Ref($close, 1) - 1 >= 0.095) & "
            "    (Ref($close, 1) / Ref($close, 2) - 1 >= 0.095) & "
            "    (Ref($close, 2) / Ref($close, 3) - 1 >= 0.095), "
            "    3, "
            "    If("
            "        ($close / Ref($close, 1) - 1 >= 0.095) & "
            "        (Ref($close, 1) / Ref($close, 2) - 1 >= 0.095), "
            "        2, "
            "        If($close / Ref($close, 1) - 1 >= 0.095, 1, 0)"
            "    )"
            ")",

            # 因子5: 涨停后封单强度（量能萎缩表示封单坚决）
            # 涨停当天，成交量相对5日均量的缩减程度
            "If("
            "    $close / Ref($close, 1) - 1 >= 0.095, "
            "    1 - ($volume / Mean($volume, 5)), "
            "    0"
            ")",
        ]

    @staticmethod
    def get_volume_price_coordination():
        """
        量价配合因子（4个）

        量价关系：
        - 价涨量增：健康上涨，持续性强
        - 价涨量缩：上涨乏力，警惕反转
        - 价跌量增：恐慌盘，可能筑底
        - 价跌量缩：阴跌，继续看空

        Returns:
            list: 4个量价配合因子表达式
        """
        return [
            # 因子6: 价涨量增（健康上涨信号）
            # 当价格上涨且成交量放大时 = 1，否则 = 0
            "If("
            "    ($close > Ref($close, 1)) & ($volume > Ref($volume, 1)), "
            "    1, "
            "    0"
            ")",

            # 因子7: 价涨量缩（上涨乏力信号）
            "If("
            "    ($close > Ref($close, 1)) & ($volume < Ref($volume, 1)), "
            "    1, "
            "    0"
            ")",

            # 因子8: 量价协同度（相关性）
            # 5日价格变化与成交量变化的相关性
            "Corr($close / Ref($close, 1) - 1, $volume / Ref($volume, 1) - 1, 5)",

            # 因子9: 放量突破信号
            # 价格突破20日均线，且成交量是5日均量的1.5倍以上
            "If("
            "    ($close > Mean($close, 20)) & "
            "    (Ref($close, 1) <= Mean(Ref($close, 1), 20)) & "
            "    ($volume > 1.5 * Mean($volume, 5)), "
            "    1, "
            "    0"
            ")",
        ]

    @staticmethod
    def get_momentum_reversal():
        """
        动量反转因子（3个）

        A股特点：
        - 短期动量效应：1-5日强者恒强
        - 中期反转效应：1-3月超涨必回调
        - 长期均值回归：6-12月回归基本面

        Returns:
            list: 3个动量反转因子表达式
        """
        return [
            # 因子10: 5日短期动量（强者恒强）
            # 过去5日累计收益率
            "$close / Ref($close, 5) - 1",

            # 因子11: 20日中期反转（超涨回调）
            # 过去20日累计收益率的负值（反转逻辑）
            "-(($close / Ref($close, 20) - 1))",

            # 因子12: 动量反转综合（短期动量 - 中期反转）
            # 短期涨幅 - 中期涨幅，捕捉短期强势但中期未过度上涨的股票
            "($close / Ref($close, 5) - 1) - ($close / Ref($close, 20) - 1)",
        ]

    @staticmethod
    def get_industry_rotation():
        """
        行业轮动因子（2个）

        A股特点：
        - 行业轮动明显：政策驱动、板块效应强
        - 相对强度：个股相对行业的超额收益

        注意：需要行业分类数据支持

        Returns:
            list: 2个行业轮动因子表达式
        """
        return [
            # 因子13: 个股相对行业强度（5日）
            # 个股5日收益 - 行业平均5日收益
            # 注：这里使用市场整体均值代替行业均值（简化实现）
            "($close / Ref($close, 5) - 1) - Mean($close / Ref($close, 5) - 1, 300)",

            # 因子14: 个股相对行业强度（20日）
            "($close / Ref($close, 20) - 1) - Mean($close / Ref($close, 20) - 1, 300)",
        ]

    @staticmethod
    def get_all_features():
        """
        获取所有A股特色因子

        Returns:
            list: 14个A股特色因子表达式
        """
        features = []
        features.extend(ChinaMarketFactors.get_limit_factors())              # 5个
        features.extend(ChinaMarketFactors.get_volume_price_coordination())  # 4个
        features.extend(ChinaMarketFactors.get_momentum_reversal())          # 3个
        features.extend(ChinaMarketFactors.get_industry_rotation())          # 2个
        return features  # 总计14个

    @staticmethod
    def get_feature_names():
        """
        获取因子名称列表（便于后续分析）

        Returns:
            list: 14个因子的简短名称
        """
        return [
            # 涨跌停板因子（5个）
            'IS_LIMIT_UP',           # 是否涨停
            'IS_LIMIT_DOWN',         # 是否跌停
            'LIMIT_UP_COUNT_5D',     # 5日涨停次数
            'CONSECUTIVE_LIMIT_UP',  # 连续涨停天数
            'LIMIT_UP_SEAL_STRENGTH',# 涨停封单强度

            # 量价配合因子（4个）
            'PRICE_UP_VOL_UP',       # 价涨量增
            'PRICE_UP_VOL_DOWN',     # 价涨量缩
            'VOL_PRICE_CORR_5D',     # 5日量价相关性
            'BREAKOUT_WITH_VOL',     # 放量突破

            # 动量反转因子（3个）
            'MOMENTUM_5D',           # 5日短期动量
            'REVERSAL_20D',          # 20日中期反转
            'MOMENTUM_REVERSAL',     # 动量反转综合

            # 行业轮动因子（2个）
            'RELATIVE_STRENGTH_5D',  # 相对强度5日
            'RELATIVE_STRENGTH_20D', # 相对强度20日
        ]

    @staticmethod
    def get_feature_descriptions():
        """
        获取因子详细描述（用于文档和报告）

        Returns:
            dict: 因子名称到描述的映射
        """
        names = ChinaMarketFactors.get_feature_names()
        descriptions = [
            "是否涨停：收盘价接近或达到9.5%涨幅",
            "是否跌停：收盘价接近或达到-9.5%跌幅",
            "5日涨停次数：过去5个交易日涨停次数统计",
            "连续涨停天数：最近连续涨停的天数（最多3天）",
            "涨停封单强度：涨停时成交量萎缩程度，值越大封单越强",

            "价涨量增：价格上涨且成交量放大的健康上涨信号",
            "价涨量缩：价格上涨但成交量缩减的上涨乏力信号",
            "5日量价相关性：价格变化与成交量变化的5日相关系数",
            "放量突破：价格突破20日均线且成交量显著放大",

            "5日短期动量：过去5日累计收益率，捕捉短期强势",
            "20日中期反转：过去20日累计收益率的负值，反转逻辑",
            "动量反转综合：短期动量减去中期动量，平衡强度与反转",

            "相对强度5日：个股5日收益相对市场平均的超额收益",
            "相对强度20日：个股20日收益相对市场平均的超额收益",
        ]

        return dict(zip(names, descriptions))


# 使用示例
if __name__ == "__main__":
    """演示因子库的使用方法"""

    # 获取所有因子表达式
    all_features = ChinaMarketFactors.get_all_features()
    print(f"共有 {len(all_features)} 个A股特色因子")

    # 获取因子名称
    feature_names = ChinaMarketFactors.get_feature_names()
    print("\n因子名称列表：")
    for i, name in enumerate(feature_names, 1):
        print(f"{i}. {name}")

    # 获取因子描述
    feature_desc = ChinaMarketFactors.get_feature_descriptions()
    print("\n因子详细描述：")
    for name, desc in feature_desc.items():
        print(f"{name}: {desc}")

    # 按分类输出因子表达式
    print("\n=== 涨跌停板因子 ===")
    for expr in ChinaMarketFactors.get_limit_factors():
        print(expr[:80] + "..." if len(expr) > 80 else expr)

    print("\n=== 量价配合因子 ===")
    for expr in ChinaMarketFactors.get_volume_price_coordination():
        print(expr[:80] + "..." if len(expr) > 80 else expr)

    print("\n=== 动量反转因子 ===")
    for expr in ChinaMarketFactors.get_momentum_reversal():
        print(expr)

    print("\n=== 行业轮动因子 ===")
    for expr in ChinaMarketFactors.get_industry_rotation():
        print(expr)
