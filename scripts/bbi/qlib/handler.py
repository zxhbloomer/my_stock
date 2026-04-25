import sys
try:
    import qlib  # noqa: F401
except ImportError:
    sys.path.insert(0, "D:/2026_project/99_github/qlib-main/qlib")

from qlib.contrib.data.handler import Alpha158


class BBIAlpha(Alpha158):
    """Alpha158 + BBI因子扩展，共173个因子。

    新增因子：
    - BBI组（6个）：基于bbi字段
    - 估值组（5个）：来自027_daily_basic
    - 筹码组（2个）：来自061_cyq_perf（2018起）
    - 资金流组（2个）：来自080_moneyflow
    """

    def get_feature_config(self):
        fields, names = super().get_feature_config()

        bbi_fields = [
            "$bbi/$close",
            "$close/$bbi - 1",
            "($bbi - Ref($bbi,1))/$bbi",
            "If($close > $bbi, 1, -1)",
            "Mean($close > $bbi, 5)",
            "Mean($close > $bbi, 20)",
        ]
        bbi_names = [
            "BBI_RATIO", "BBI_DEV", "BBI_SLOPE",
            "BBI_CROSS", "BBI_CROSS5", "BBI_CROSS20",
        ]

        val_fields = [
            "$pe_ttm",
            "$pb",
            "$turnover",
            "Rank($pe_ttm, 20)",
            "Rank($turnover, 20)",
        ]
        val_names = ["PE_TTM", "PB", "TURNOVER", "PE_RANK20", "TURN_RANK20"]

        chip_fields = [
            "$winner_rate",
            "$cost_avg / $close - 1",
        ]
        chip_names = ["WINNER_RATE", "COST_DEV"]

        flow_fields = [
            "$net_mf / ($volume * $close + 1e-12)",
            "Mean($net_mf, 5) / ($volume * $close + 1e-12)",
        ]
        flow_names = ["MF_RATIO", "MF_RATIO5"]

        fields += bbi_fields + val_fields + chip_fields + flow_fields
        names += bbi_names + val_names + chip_names + flow_names

        return fields, names
