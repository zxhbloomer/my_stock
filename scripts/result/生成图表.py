"""
使用matplotlib生成静态图表
适合Windows命令行环境
"""
import qlib
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
from pathlib import Path
from qlib.workflow import R
import yaml

# 设置中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False
# 使用Agg后端(非交互式)
matplotlib.use('Agg')

# 初始化Qlib
qlib.init(provider_uri="D:/Data/my_stock", region="cn")

def find_latest_backtest():
    """查找最新的回测记录"""
    mlruns_dir = Path("mlruns")
    for exp_dir in mlruns_dir.iterdir():
        if not exp_dir.is_dir():
            continue
        meta_file = exp_dir / "meta.yaml"
        if not meta_file.exists():
            continue

        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = yaml.safe_load(f)

        if meta.get('name') == 'backtest_analysis':
            run_dirs = [d for d in exp_dir.iterdir() if d.is_dir()]
            if run_dirs:
                latest_run = max(run_dirs, key=lambda x: x.stat().st_mtime)
                return latest_run.name, "backtest_analysis"
    return None, None

def create_charts():
    """生成所有图表"""
    recorder_id, exp_name = find_latest_backtest()
    if not recorder_id:
        print("错误: 未找到回测记录")
        return

    print(f"加载回测记录: {recorder_id}\n")
    recorder = R.get_recorder(recorder_id=recorder_id, experiment_name=exp_name)

    # 加载数据
    pred_df = recorder.load_object("pred.pkl")
    label_df = recorder.load_object("label.pkl")
    report_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
    analysis_df = recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")

    # 合并预测和标签
    pred_label = pd.concat([label_df, pred_df], axis=1, sort=True).reindex(label_df.index)
    if isinstance(pred_label.columns, pd.MultiIndex):
        pred_label.columns = ['label', 'score']
    else:
        pred_label.columns = ['label', 'score']

    # 创建图表
    fig = plt.figure(figsize=(20, 12))

    # 1. IC时间序列
    ax1 = plt.subplot(3, 3, 1)
    ic_series = pred_label.groupby(level=0).apply(lambda x: x['label'].corr(x['score']))
    ic_series.plot(ax=ax1, linewidth=1, color='blue', alpha=0.7)
    ax1.axhline(0, color='red', linestyle='--', alpha=0.5)
    ax1.set_title('IC时间序列', fontsize=12, fontweight='bold')
    ax1.set_xlabel('日期')
    ax1.set_ylabel('IC值')
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis='x', rotation=45)

    # 2. IC分布直方图
    ax2 = plt.subplot(3, 3, 2)
    ic_series.hist(bins=50, ax=ax2, edgecolor='black', alpha=0.7)
    ax2.set_title('IC分布', fontsize=12, fontweight='bold')
    ax2.set_xlabel('IC值')
    ax2.set_ylabel('频数')
    ax2.axvline(ic_series.mean(), color='red', linestyle='--', label=f'平均IC: {ic_series.mean():.4f}')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 3. 累积收益曲线
    ax3 = plt.subplot(3, 3, 3)
    cumulative_return = (1 + report_df['return']).cumprod()
    cumulative_bench = (1 + report_df['bench']).cumprod()
    cumulative_return.plot(ax=ax3, label='策略收益', linewidth=2, color='blue')
    cumulative_bench.plot(ax=ax3, label='基准收益', linewidth=2, color='gray', alpha=0.7)
    ax3.set_title('累积收益曲线', fontsize=12, fontweight='bold')
    ax3.set_xlabel('日期')
    ax3.set_ylabel('累积收益')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    ax3.tick_params(axis='x', rotation=45)

    # 4. 超额收益(无成本)
    ax4 = plt.subplot(3, 3, 4)
    excess_return = report_df['return'] - report_df['bench']
    cumulative_excess = (1 + excess_return).cumprod()
    cumulative_excess.plot(ax=ax4, linewidth=2, color='green')
    ax4.set_title('超额收益(无成本)', fontsize=12, fontweight='bold')
    ax4.set_xlabel('日期')
    ax4.set_ylabel('累积超额收益')
    ax4.grid(True, alpha=0.3)
    ax4.tick_params(axis='x', rotation=45)

    # 5. 超额收益(含成本)
    ax5 = plt.subplot(3, 3, 5)
    excess_return_with_cost = report_df['return'] - report_df['bench'] - report_df['cost']
    cumulative_excess_cost = (1 + excess_return_with_cost).cumprod()
    cumulative_excess_cost.plot(ax=ax5, linewidth=2, color='orange')
    ax5.set_title('超额收益(含成本)', fontsize=12, fontweight='bold')
    ax5.set_xlabel('日期')
    ax5.set_ylabel('累积超额收益')
    ax5.grid(True, alpha=0.3)
    ax5.tick_params(axis='x', rotation=45)

    # 6. 回撤曲线
    ax6 = plt.subplot(3, 3, 6)
    cumulative = (1 + report_df['return']).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    drawdown.plot(ax=ax6, linewidth=2, color='red', alpha=0.7)
    ax6.fill_between(drawdown.index, 0, drawdown, alpha=0.3, color='red')
    ax6.set_title('回撤曲线', fontsize=12, fontweight='bold')
    ax6.set_xlabel('日期')
    ax6.set_ylabel('回撤幅度')
    ax6.grid(True, alpha=0.3)
    ax6.tick_params(axis='x', rotation=45)

    # 7. 预测分数分布
    ax7 = plt.subplot(3, 3, 7)
    pred_df.hist(bins=50, ax=ax7, edgecolor='black', alpha=0.7)
    ax7.set_title('预测分数分布', fontsize=12, fontweight='bold')
    ax7.set_xlabel('预测分数')
    ax7.set_ylabel('频数')
    ax7.axvline(0, color='red', linestyle='--', alpha=0.5)
    ax7.grid(True, alpha=0.3)

    # 8. 每日换手率
    ax8 = plt.subplot(3, 3, 8)
    report_df['turnover'].plot(ax=ax8, linewidth=1, color='purple', alpha=0.7)
    ax8.set_title('每日换手率', fontsize=12, fontweight='bold')
    ax8.set_xlabel('日期')
    ax8.set_ylabel('换手率')
    ax8.grid(True, alpha=0.3)
    ax8.tick_params(axis='x', rotation=45)

    # 9. 年化指标对比
    ax9 = plt.subplot(3, 3, 9)
    metrics = {
        '年化收益\n(无成本)': analysis_df.loc[('excess_return_without_cost', 'annualized_return'), 'risk'],
        '年化收益\n(含成本)': analysis_df.loc[('excess_return_with_cost', 'annualized_return'), 'risk'],
        '信息比率\n(无成本)': analysis_df.loc[('excess_return_without_cost', 'information_ratio'), 'risk'],
        '信息比率\n(含成本)': analysis_df.loc[('excess_return_with_cost', 'information_ratio'), 'risk'],
    }
    colors = ['#2ecc71', '#27ae60', '#3498db', '#2980b9']
    bars = ax9.bar(range(len(metrics)), list(metrics.values()), color=colors, alpha=0.7, edgecolor='black')
    ax9.set_xticks(range(len(metrics)))
    ax9.set_xticklabels(list(metrics.keys()), fontsize=9)
    ax9.set_title('关键指标对比', fontsize=12, fontweight='bold')
    ax9.set_ylabel('数值')
    ax9.grid(True, alpha=0.3, axis='y')

    # 在柱状图上添加数值标签
    for i, (bar, value) in enumerate(zip(bars, metrics.values())):
        ax9.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f'{value:.3f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    plt.suptitle('Qlib量化策略回测分析报告', fontsize=18, fontweight='bold', y=0.995)
    plt.tight_layout()

    # 保存图表
    output_file = "backtest_analysis.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"[OK] 图表已保存: {output_file}")
    print(f"   图表包含9个分析视图:")
    print(f"   1. IC时间序列")
    print(f"   2. IC分布")
    print(f"   3. 累积收益曲线")
    print(f"   4. 超额收益(无成本)")
    print(f"   5. 超额收益(含成本)")
    print(f"   6. 回撤曲线")
    print(f"   7. 预测分数分布")
    print(f"   8. 每日换手率")
    print(f"   9. 关键指标对比")
    print(f"\n请打开 {output_file} 查看完整分析报告")

if __name__ == "__main__":
    print("正在生成分析图表...\n")
    create_charts()
