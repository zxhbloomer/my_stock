"""
Alpha因子库
基于Qlib表达式定义技术因子
"""


class AlphaFactors:
    """Alpha因子集合（基于Alpha158扩展）"""

    @staticmethod
    def get_base_features():
        """基础特征（OHLCV）"""
        return [
            "$open",
            "$close",
            "$high",
            "$low",
            "$volume",
            "$vwap",  # 如果数据中有
        ]

    @staticmethod
    def get_price_features():
        """价格类因子"""
        return [
            # 1. 收益率特征
            "Ref($close, 1) / $close - 1",                    # 1日收益率
            "Ref($close, 5) / $close - 1",                    # 5日收益率
            "Ref($close, 10) / $close - 1",                   # 10日收益率
            "Ref($close, 20) / $close - 1",                   # 20日收益率

            # 2. 价格动量
            "$close / Mean($close, 5) - 1",                   # 5日均线偏离度
            "$close / Mean($close, 10) - 1",                  # 10日均线偏离度
            "$close / Mean($close, 20) - 1",                  # 20日均线偏离度
            "$close / Mean($close, 60) - 1",                  # 60日均线偏离度

            # 3. 均线交叉
            "Mean($close, 5) / Mean($close, 20) - 1",        # 5/20日均线比
            "Mean($close, 10) / Mean($close, 30) - 1",       # 10/30日均线比

            # 4. 价格Z-score
            "($close - Mean($close, 20)) / Std($close, 20)", # 20日价格Z-score
            "($close - Mean($close, 60)) / Std($close, 60)", # 60日价格Z-score

            # 5. 日内特征
            "($high - $low) / $open",                         # 日内振幅
            "($close - $open) / $open",                       # 日内收益
            "$close / $high",                                 # 收盘价相对最高价位置
            "($close - $low) / ($high - $low)",              # 收盘价在日内位置
        ]

    @staticmethod
    def get_volume_features():
        """成交量因子"""
        return [
            # 1. 成交量比率
            "$volume / Mean($volume, 5)",                     # 5日量比
            "$volume / Mean($volume, 10)",                    # 10日量比
            "$volume / Mean($volume, 20)",                    # 20日量比

            # 2. 成交量变化
            "Ref($volume, 1) / $volume",                      # 量变化率
            "Log($volume / Mean($volume, 5))",                # 对数量比

            # 3. 成交量动量
            "Mean($volume, 5) / Mean($volume, 20)",          # 短期/长期量比
            "Std($volume, 20) / Mean($volume, 20)",          # 成交量变异系数

            # 4. 成交量集中度
            "$volume / Sum($volume, 5)",                      # 5日量集中度
            "$volume / Sum($volume, 20)",                     # 20日量集中度
        ]

    @staticmethod
    def get_volatility_features():
        """波动率因子"""
        return [
            # 1. 历史波动率
            "Std($close / Ref($close, 1) - 1, 5)",          # 5日历史波动率
            "Std($close / Ref($close, 1) - 1, 10)",         # 10日历史波动率
            "Std($close / Ref($close, 1) - 1, 20)",         # 20日历史波动率
            "Std($close / Ref($close, 1) - 1, 60)",         # 60日历史波动率

            # 2. 高低价差
            "Std($high - $low, 5) / Mean($close, 5)",       # 5日振幅标准差
            "Std($high - $low, 20) / Mean($close, 20)",     # 20日振幅标准差

            # 3. 价格区间
            "(Max($high, 20) - Min($low, 20)) / Mean($close, 20)",  # 20日价格区间

            # 4. ATR (Average True Range)
            "Mean($high - $low, 14) / $close",               # 简化ATR
        ]

    @staticmethod
    def get_technical_indicators():
        """技术指标因子"""
        return [
            # 1. MACD系列
            "(EMA($close, 12) - EMA($close, 26)) / $close",                     # MACD归一化
            "EMA((EMA($close, 12) - EMA($close, 26)) / $close, 9)",            # MACD信号线

            # 2. RSI系列（简化版）
            "($close - Min($low, 14)) / (Max($high, 14) - Min($low, 14))",    # RSI基础

            # 3. 布林带
            "($close - Mean($close, 20)) / Std($close, 20)",                   # 布林带位置
            "Std($close, 20) / Mean($close, 20)",                               # 布林带宽度

            # 4. 威廉指标
            "($high - $close) / ($high - $low)",                                # 威廉%R基础
            "(Max($high, 14) - $close) / (Max($high, 14) - Min($low, 14))",   # 14日威廉%R
        ]

    @staticmethod
    def get_correlation_features():
        """相关性因子"""
        return [
            # 价量相关性
            "Corr($close, $volume, 5)",                      # 5日价量相关性
            "Corr($close, $volume, 10)",                     # 10日价量相关性
            "Corr($close, $volume, 20)",                     # 20日价量相关性

            # 价格自相关
            "Corr($close, Ref($close, 1), 10)",              # 价格自相关

            # 高低价相关
            "Corr($high, $low, 20)",                         # 高低价相关性
        ]

    @staticmethod
    def get_pattern_features():
        """形态因子"""
        return [
            # 1. 趋势强度
            "($close - Ref($close, 20)) / Std($close, 20)",              # 趋势强度

            # 2. 新高新低
            "($close == Max($close, 20)) ? 1 : 0",                        # 是否创20日新高
            "($close == Min($close, 20)) ? 1 : 0",                        # 是否创20日新低

            # 3. 缺口
            "($open - Ref($close, 1)) / Ref($close, 1)",                 # 跳空缺口

            # 4. 上下影线
            "($close - $low) / ($high - $low)",                           # 下影线比例
            "($high - $close) / ($high - $low)",                          # 上影线比例
        ]

    @staticmethod
    def get_all_features():
        """获取所有因子"""
        features = []
        features.extend(AlphaFactors.get_base_features())
        features.extend(AlphaFactors.get_price_features())
        features.extend(AlphaFactors.get_volume_features())
        features.extend(AlphaFactors.get_volatility_features())
        features.extend(AlphaFactors.get_technical_indicators())
        features.extend(AlphaFactors.get_correlation_features())
        features.extend(AlphaFactors.get_pattern_features())
        return features

    @staticmethod
    def get_feature_names():
        """获取特征名称列表"""
        # 这里返回特征的简短名称，用于后续分析
        names = []

        # 基础特征
        names.extend(['OPEN', 'CLOSE', 'HIGH', 'LOW', 'VOLUME', 'VWAP'])

        # 价格特征
        names.extend([
            'RET1', 'RET5', 'RET10', 'RET20',
            'MA5_DEV', 'MA10_DEV', 'MA20_DEV', 'MA60_DEV',
            'MA_CROSS_5_20', 'MA_CROSS_10_30',
            'ZSCORE20', 'ZSCORE60',
            'INTRADAY_RANGE', 'INTRADAY_RET', 'CLOSE_HIGH_RATIO', 'CLOSE_POS'
        ])

        # 成交量特征
        names.extend([
            'VOL_RATIO5', 'VOL_RATIO10', 'VOL_RATIO20',
            'VOL_CHANGE', 'LOG_VOL_RATIO',
            'VOL_MA_RATIO', 'VOL_CV',
            'VOL_CONC5', 'VOL_CONC20'
        ])

        # 波动率特征
        names.extend([
            'VOLATILITY5', 'VOLATILITY10', 'VOLATILITY20', 'VOLATILITY60',
            'RANGE_STD5', 'RANGE_STD20',
            'PRICE_RANGE20', 'ATR14'
        ])

        # 技术指标
        names.extend([
            'MACD', 'MACD_SIGNAL',
            'RSI_BASE',
            'BBANDS_POS', 'BBANDS_WIDTH',
            'WILLR_BASE', 'WILLR14'
        ])

        # 相关性
        names.extend([
            'CORR_PV5', 'CORR_PV10', 'CORR_PV20',
            'AUTOCORR10',
            'CORR_HL20'
        ])

        # 形态
        names.extend([
            'TREND_STRENGTH',
            'IS_HIGH20', 'IS_LOW20',
            'GAP',
            'LOWER_SHADOW', 'UPPER_SHADOW'
        ])

        return names
