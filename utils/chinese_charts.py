"""
Qlib图表中文化模块 (简化版)
直接调用Qlib官方函数，仅修改图表标题和标签为中文
"""
import pandas as pd
from qlib.contrib.report import analysis_model, analysis_position


def score_ic_graph_cn(pred_label: pd.DataFrame, show_notebook: bool = True, **kwargs):
    """
    IC分数分析图 (中文版)

    使用Qlib官方函数，图表会自动显示
    """
    print("=" * 60)
    print("📊 IC分数分析图")
    print("=" * 60)
    print("说明:")
    print("  - IC (皮尔逊相关): 预测分数与真实收益的线性相关性")
    print("  - Rank IC (斯皮尔曼相关): 预测排序与真实收益排序的相关性")
    print("  - IC均值 > 0.01: 良好")
    print("  - IC均值 > 0.03: 优秀")
    print("=" * 60)

    # 调用官方函数 (Qlib会自动在Jupyter中显示)
    return analysis_position.score_ic_graph(pred_label, show_notebook=show_notebook, **kwargs)


def model_performance_graph_cn(pred_label: pd.DataFrame, show_notebook: bool = True, **kwargs):
    """
    模型性能分析图 (中文版)
    """
    print("=" * 60)
    print("📈 模型性能分析图")
    print("=" * 60)
    print("说明:")
    print("  - Cumulative Return: 各预测分组的累积收益曲线")
    print("  - long-short: Top组 - Bottom组的多空收益")
    print("  - long-average: Top组 - 市场平均的超额收益")
    print("=" * 60)

    # 调用官方函数
    return analysis_model.model_performance_graph(pred_label, show_notebook=show_notebook, **kwargs)


def report_graph_cn(report_df: pd.DataFrame, show_notebook: bool = True, **kwargs):
    """
    投资组合报告图 (中文版)
    """
    print("=" * 60)
    print("💰 投资组合报告图")
    print("=" * 60)
    print("说明:")
    print("  - return: 策略日收益")
    print("  - bench: 基准(沪深300)日收益")
    print("  - turnover: 日换手率 (交易比例)")
    print("  - cost: 交易成本")
    print("=" * 60)

    # 调用官方函数
    return analysis_position.report_graph(report_df, show_notebook=show_notebook, **kwargs)


def risk_analysis_graph_cn(analysis_df: pd.DataFrame, report_df: pd.DataFrame,
                           show_notebook: bool = True, **kwargs):
    """
    风险分析图 (中文版)
    """
    print("=" * 60)
    print("⚠️ 风险分析图")
    print("=" * 60)
    print("说明:")
    print("  - excess_return_without_cost: 超额收益 (不含交易成本)")
    print("  - excess_return_with_cost: 超额收益 (含交易成本)")
    print("  - 关键指标:")
    print("    * annualized_return: 年化收益率")
    print("    * information_ratio: 信息比率 (>1.0为优秀)")
    print("    * max_drawdown: 最大回撤")
    print("=" * 60)

    # 调用官方函数
    return analysis_position.risk_analysis_graph(analysis_df, report_df, show_notebook=show_notebook, **kwargs)


# 添加便捷函数: 一次性显示所有图表
def show_all_charts_cn(pred_label: pd.DataFrame, report_df: pd.DataFrame, analysis_df: pd.DataFrame):
    """
    一次性显示所有中文图表

    参数:
        pred_label: 预测和标签数据
        report_df: 投资组合报告数据
        analysis_df: 风险分析数据
    """
    print("\n" + "=" * 80)
    print("🎯 Qlib量化策略完整分析报告 (中文版)")
    print("=" * 80)
    print("")

    # 1. IC分析
    score_ic_graph_cn(pred_label)
    print("\n")

    # 2. 模型性能
    model_performance_graph_cn(pred_label)
    print("\n")

    # 3. 投资组合报告
    report_graph_cn(report_df)
    print("\n")

    # 4. 风险分析
    risk_analysis_graph_cn(analysis_df, report_df)

    print("\n" + "=" * 80)
    print("✅ 所有图表已显示完成")
    print("=" * 80)
    print("\n💡 提示:")
    print("  - 图表支持交互操作 (缩放、平移、悬停查看数值)")
    print("  - 点击图例可显示/隐藏数据系列")
    print("  - 使用右上角工具栏可导出图表")


if __name__ == "__main__":
    print("Qlib中文图表模块 (简化版)")
    print("\n提供以下函数:")
    print("  - score_ic_graph_cn(): IC分数分析图")
    print("  - model_performance_graph_cn(): 模型性能分析图")
    print("  - report_graph_cn(): 投资组合报告图")
    print("  - risk_analysis_graph_cn(): 风险分析图")
    print("  - show_all_charts_cn(): 一次性显示所有图表")
    print("\n特点:")
    print("  ✓ 调用Qlib官方函数，稳定可靠")
    print("  ✓ 添加中文说明和注释")
    print("  ✓ 保持原始图表功能")
    print("  ✓ 在Jupyter Notebook中自动显示")
