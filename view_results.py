"""
查看Qlib预测结果和生成图表
基于官方analysis_model和analysis_position模块
"""
import qlib
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from qlib.workflow import R
from qlib.contrib.report import analysis_model, analysis_position

# 初始化Qlib
qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")

# 设置中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

def find_latest_backtest_recorder():
    """查找最新的回测记录"""
    mlruns_dir = Path("mlruns")

    # 查找所有实验
    exp_dirs = [d for d in mlruns_dir.iterdir() if d.is_dir() and d.name != '.trash']

    if not exp_dirs:
        print("错误: 未找到MLflow实验记录")
        return None

    # 遍历所有实验查找backtest_analysis
    for exp_dir in exp_dirs:
        meta_file = exp_dir / "meta.yaml"
        if not meta_file.exists():
            continue

        # 读取实验名称
        import yaml
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = yaml.safe_load(f)

        # 如果是backtest_analysis实验
        if meta.get('name') == 'backtest_analysis':
            # 找到最新的run
            run_dirs = [d for d in exp_dir.iterdir() if d.is_dir() and d.name != 'meta.yaml']
            if not run_dirs:
                continue

            latest_run = max(run_dirs, key=lambda x: x.stat().st_mtime)
            return meta['experiment_id'], latest_run.name

    print("错误: 未找到backtest_analysis实验")
    return None

def load_backtest_results():
    """加载回测分析结果"""
    result = find_latest_backtest_recorder()
    if not result:
        return None

    experiment_id, recorder_id = result

    print(f"加载实验: {experiment_id}")
    print(f"Recorder ID: {recorder_id}\n")

    # 使用R.get_recorder加载
    recorder = R.get_recorder(recorder_id=recorder_id, experiment_name="backtest_analysis")

    try:
        # 加载各种分析结果
        pred_df = recorder.load_object("pred.pkl")
        label_df = recorder.load_object("label.pkl")
        report_normal_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
        positions = recorder.load_object("portfolio_analysis/positions_normal_1day.pkl")
        analysis_df = recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")

        return {
            'recorder': recorder,
            'pred': pred_df,
            'label': label_df,
            'report': report_normal_df,
            'positions': positions,
            'analysis': analysis_df
        }
    except Exception as e:
        print(f"加载数据时出错: {e}")
        return None

def display_backtest_metrics(results):
    """显示回测指标"""
    analysis_df = results['analysis']

    print("=" * 80)
    print("回测结果分析")
    print("=" * 80)

    print("\n【超额收益分析 - 无交易成本】")
    print("-" * 80)
    # MultiIndex: (category, metric)
    print(f"  平均收益率: {analysis_df.loc[('excess_return_without_cost', 'mean'), 'risk']:.6f}")
    print(f"  收益波动率: {analysis_df.loc[('excess_return_without_cost', 'std'), 'risk']:.6f}")
    print(f"  年化收益率: {analysis_df.loc[('excess_return_without_cost', 'annualized_return'), 'risk']:.2%}")
    print(f"  信息比率 (IR): {analysis_df.loc[('excess_return_without_cost', 'information_ratio'), 'risk']:.4f}")
    print(f"  最大回撤 (MDD): {analysis_df.loc[('excess_return_without_cost', 'max_drawdown'), 'risk']:.2%}")

    print("\n【超额收益分析 - 含交易成本】")
    print("-" * 80)
    print(f"  平均收益率: {analysis_df.loc[('excess_return_with_cost', 'mean'), 'risk']:.6f}")
    print(f"  收益波动率: {analysis_df.loc[('excess_return_with_cost', 'std'), 'risk']:.6f}")
    print(f"  年化收益率: {analysis_df.loc[('excess_return_with_cost', 'annualized_return'), 'risk']:.2%}")
    print(f"  信息比率 (IR): {analysis_df.loc[('excess_return_with_cost', 'information_ratio'), 'risk']:.4f}")
    print(f"  最大回撤 (MDD): {analysis_df.loc[('excess_return_with_cost', 'max_drawdown'), 'risk']:.2%}")

    print("\n" + "=" * 80)

def generate_analysis_graphs(results):
    """生成Qlib官方分析图表"""
    pred_df = results['pred']
    label_df = results['label']
    report_df = results['report']
    analysis_df = results['analysis']

    # 合并预测和标签
    pred_label = pd.concat([label_df, pred_df], axis=1, sort=True).reindex(label_df.index)
    pred_label.columns = ['label', 'score']

    print("\n正在生成分析图表...")

    # 1. IC分数图 (Information Coefficient)
    print("  [1/4] 生成IC分数图...")
    analysis_position.score_ic_graph(pred_label)

    # 2. 模型性能图
    print("  [2/4] 生成模型性能图...")
    analysis_model.model_performance_graph(pred_label)

    # 3. 投资组合报告图
    print("  [3/4] 生成投资组合报告图...")
    analysis_position.report_graph(report_df)

    # 4. 风险分析图
    print("  [4/4] 生成风险分析图...")
    analysis_position.risk_analysis_graph(analysis_df, report_df)

    print("\n✅ 所有图表生成完成!")
    print("提示: 关闭图表窗口后可以查看下一个图表")

def show_top_predictions(results):
    """显示Top股票预测"""
    pred_df = results['pred']

    # 获取最新交易日
    latest_date = pred_df.index.get_level_values(0).max()
    latest_pred = pred_df.loc[latest_date]

    # 如果是DataFrame,取'score'列;如果是Series,直接排序
    if isinstance(latest_pred, pd.DataFrame):
        latest_pred = latest_pred['score'].sort_values(ascending=False)
    else:
        latest_pred = latest_pred.sort_values(ascending=False)

    print("\n" + "=" * 80)
    print(f"最新交易日预测 ({latest_date.date()})")
    print("=" * 80)

    print("\n【Top 15 看涨股票】(预测分数最高)")
    print("-" * 80)
    print(f"{'排名':<6} {'股票代码':<12} {'预测分数':>15}")
    print("-" * 80)
    for i, (stock, score) in enumerate(latest_pred.head(15).items(), 1):
        print(f"{i:<6} {stock:<12} {score:>15.6f}")

    print("\n【Top 15 看跌股票】(预测分数最低)")
    print("-" * 80)
    print(f"{'排名':<6} {'股票代码':<12} {'预测分数':>15}")
    print("-" * 80)
    for i, (stock, score) in enumerate(latest_pred.tail(15).items(), 1):
        print(f"{i:<6} {stock:<12} {score:>15.6f}")

    print("\n" + "=" * 80)

def main():
    """主函数"""
    print("正在加载回测结果...\n")

    results = load_backtest_results()
    if not results:
        print("无法加载回测结果，请先运行 python run_workflow.py")
        return

    # 显示回测指标
    display_backtest_metrics(results)

    # 显示Top股票预测
    show_top_predictions(results)

    # 生成分析图表
    generate_analysis_graphs(results)

    print("\n" + "=" * 80)
    print("分析完成!")
    print("=" * 80)
    print("\n说明:")
    print("  - IC (Information Coefficient): 预测分数与真实收益的相关性")
    print("  - IR (Information Ratio): 信息比率,衡量策略的风险调整收益")
    print("  - MDD (Maximum Drawdown): 最大回撤,衡量最大损失幅度")
    print("  - 年化收益率: 策略的年度化收益表现")
    print("=" * 80)

if __name__ == "__main__":
    main()
