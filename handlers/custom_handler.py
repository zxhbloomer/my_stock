"""
自定义数据Handler
继承Alpha158，在其基础上扩展 BBI 相关因子
"""
from qlib.contrib.data.handler import Alpha158


class BBIAlphaHandler(Alpha158):
    """
    BBI扩展Handler
    Alpha158（158个技术因子）+ BBI多空均线相关因子（5个）
    """

    def get_feature_config(self):
        base_fields, base_names = super().get_feature_config()

        bbi_expr = "(Mean($close,3)+Mean($close,6)+Mean($close,12)+Mean($close,24))/4"

        bbi_fields = [
            # 1. BBI值（归一化）
            f"({bbi_expr})/$close",
            # 2. 价格偏离BBI幅度（核心信号）
            f"$close/({bbi_expr})-1",
            # 3. BBI斜率（5日变化率，判断趋势方向）
            f"({bbi_expr})/Ref({bbi_expr},5)-1",
            # 4. 价格连续在BBI上方天数（10日内）
            f"Sum(If($close>({bbi_expr}),1,0),10)/10",
            # 5. BBI布林带位置（价格偏离BBI的标准差倍数）
            f"($close-({bbi_expr}))/Std({bbi_expr},11)",
        ]
        bbi_names = ["BBI", "BBI_DEV", "BBI_SLOPE", "BBI_ABOVE_RATIO", "BBI_BOLL"]

        all_fields = list(base_fields) + bbi_fields
        all_names = list(base_names) + bbi_names

        return all_fields, all_names
