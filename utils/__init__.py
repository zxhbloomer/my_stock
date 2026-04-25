"""
Qlib量化工具包
包含自定义的图表可视化和其他实用工具
"""

try:
    from .chinese_charts import (
        score_ic_graph_cn,
        model_performance_graph_cn,
        report_graph_cn,
        risk_analysis_graph_cn,
        show_all_charts_cn,
    )
    __all__ = [
        "score_ic_graph_cn",
        "model_performance_graph_cn",
        "report_graph_cn",
        "risk_analysis_graph_cn",
        "show_all_charts_cn",
    ]
except ImportError:
    # qlib 未安装时，跳过 Qlib 图表导入
    __all__ = []
