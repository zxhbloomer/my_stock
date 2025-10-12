"""
自定义数据Handler
继承Alpha158，扩展自定义因子
"""
from qlib.contrib.data.handler import Alpha158
from factors.alpha_factors import AlphaFactors


class CustomAlphaHandler(Alpha158):
    """
    自定义Alpha因子Handler
    基于Alpha158扩展
    """

    def __init__(self, **kwargs):
        """
        初始化Handler

        Args:
            instruments: 股票池 (csi300/csi500/all)
            start_time: 开始时间
            end_time: 结束时间
            fit_start_time: 拟合开始时间
            fit_end_time: 拟合结束时间
            infer_processors: 推理处理器
            learn_processors: 学习处理器
        """
        super().__init__(**kwargs)

    def get_feature_config(self):
        """
        获取特征配置
        覆盖父类方法，添加自定义因子

        Returns:
            特征表达式列表
        """
        # 获取Alpha158的基础因子
        base_features = super().get_feature_config()

        # 添加自定义Alpha因子
        custom_features = AlphaFactors.get_all_features()

        # 合并特征（去重）
        all_features = list(set(base_features + custom_features))

        return all_features


class SimpleAlphaHandler(Alpha158):
    """
    简化版Alpha因子Handler
    只包含核心因子，用于快速实验
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_feature_config(self):
        """获取简化的特征配置"""
        features = []

        # 基础特征
        features.extend(AlphaFactors.get_base_features())

        # 价格特征（精选）
        features.extend([
            "Ref($close, 1) / $close - 1",
            "Ref($close, 5) / $close - 1",
            "$close / Mean($close, 5) - 1",
            "$close / Mean($close, 20) - 1",
            "($close - Mean($close, 20)) / Std($close, 20)",
        ])

        # 成交量特征（精选）
        features.extend([
            "$volume / Mean($volume, 5)",
            "$volume / Mean($volume, 20)",
            "Log($volume / Mean($volume, 5))",
        ])

        # 波动率特征（精选）
        features.extend([
            "Std($close / Ref($close, 1) - 1, 20)",
            "($high - $low) / $open",
        ])

        # 技术指标（精选）
        features.extend([
            "(EMA($close, 12) - EMA($close, 26)) / $close",
            "($close - Mean($close, 20)) / Std($close, 20)",
        ])

        return features
