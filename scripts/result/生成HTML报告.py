"""
生成交互式HTML图表
使用plotly生成可交互的HTML报告
"""
import qlib
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from qlib.workflow import R
import yaml

def _ensure_qlib_initialized():
    """确保Qlib已初始化(避免重复初始化)"""
    try:
        # 检查Qlib是否已经初始化
        # 如果已初始化,qlib.config.C应该有provider_uri属性
        if hasattr(qlib.config.C, 'provider_uri') and qlib.config.C.provider_uri:
            # 已经初始化,直接返回
            return
    except:
        pass

    # 未初始化则执行初始化
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

def create_html_report(output_file="backtest_report.html", auto_open=True):
    """生成交互式HTML分析报告"""
    _ensure_qlib_initialized()  # 确保Qlib已初始化
    recorder_id, exp_name = find_latest_backtest()
    if not recorder_id:
        print("错误: 未找到回测记录")
        return None

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

    # 创建子图布局 (3行3列)
    fig = make_subplots(
        rows=3, cols=3,
        subplot_titles=(
            'IC时间序列', 'IC分布直方图', '累积收益曲线',
            '超额收益(无成本)', '超额收益(含成本)', '回撤曲线',
            '预测分数分布', '每日换手率', '关键指标对比'
        ),
        specs=[
            [{"type": "scatter"}, {"type": "histogram"}, {"type": "scatter"}],
            [{"type": "scatter"}, {"type": "scatter"}, {"type": "scatter"}],
            [{"type": "histogram"}, {"type": "scatter"}, {"type": "bar"}]
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.10
    )

    # 1. IC时间序列
    ic_series = pred_label.groupby(level=0).apply(lambda x: x['label'].corr(x['score']))
    fig.add_trace(
        go.Scatter(x=ic_series.index, y=ic_series.values,
                   mode='lines', name='IC值',
                   line=dict(color='blue', width=1)),
        row=1, col=1
    )
    fig.add_hline(y=0, line_dash="dash", line_color="red", opacity=0.5, row=1, col=1)

    # 2. IC分布
    fig.add_trace(
        go.Histogram(x=ic_series.values, nbinsx=50,
                     name='IC分布', marker_color='steelblue',
                     opacity=0.7),
        row=1, col=2
    )
    fig.add_vline(x=ic_series.mean(), line_dash="dash",
                  line_color="red",
                  annotation_text=f'平均: {ic_series.mean():.4f}',
                  row=1, col=2)

    # 3. 累积收益曲线
    cumulative_return = (1 + report_df['return']).cumprod()
    cumulative_bench = (1 + report_df['bench']).cumprod()
    fig.add_trace(
        go.Scatter(x=cumulative_return.index, y=cumulative_return.values,
                   mode='lines', name='策略收益',
                   line=dict(color='blue', width=2)),
        row=1, col=3
    )
    fig.add_trace(
        go.Scatter(x=cumulative_bench.index, y=cumulative_bench.values,
                   mode='lines', name='基准收益',
                   line=dict(color='gray', width=2, dash='dash')),
        row=1, col=3
    )

    # 4. 超额收益(无成本)
    excess_return = report_df['return'] - report_df['bench']
    cumulative_excess = (1 + excess_return).cumprod()
    fig.add_trace(
        go.Scatter(x=cumulative_excess.index, y=cumulative_excess.values,
                   mode='lines', name='超额收益(无成本)',
                   line=dict(color='green', width=2)),
        row=2, col=1
    )

    # 5. 超额收益(含成本)
    excess_return_with_cost = report_df['return'] - report_df['bench'] - report_df['cost']
    cumulative_excess_cost = (1 + excess_return_with_cost).cumprod()
    fig.add_trace(
        go.Scatter(x=cumulative_excess_cost.index, y=cumulative_excess_cost.values,
                   mode='lines', name='超额收益(含成本)',
                   line=dict(color='orange', width=2)),
        row=2, col=2
    )

    # 6. 回撤曲线
    cumulative = (1 + report_df['return']).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    fig.add_trace(
        go.Scatter(x=drawdown.index, y=drawdown.values,
                   mode='lines', name='回撤',
                   fill='tozeroy',
                   line=dict(color='red', width=2)),
        row=2, col=3
    )

    # 7. 预测分数分布
    fig.add_trace(
        go.Histogram(x=pred_df.values.flatten(), nbinsx=50,
                     name='预测分数', marker_color='purple',
                     opacity=0.7),
        row=3, col=1
    )
    fig.add_vline(x=0, line_dash="dash", line_color="red", opacity=0.5, row=3, col=1)

    # 8. 每日换手率
    fig.add_trace(
        go.Scatter(x=report_df.index, y=report_df['turnover'].values,
                   mode='lines', name='换手率',
                   line=dict(color='purple', width=1)),
        row=3, col=2
    )

    # 9. 关键指标对比
    metrics = {
        '年化收益<br>(无成本)': analysis_df.loc[('excess_return_without_cost', 'annualized_return'), 'risk'],
        '年化收益<br>(含成本)': analysis_df.loc[('excess_return_with_cost', 'annualized_return'), 'risk'],
        '信息比率<br>(无成本)': analysis_df.loc[('excess_return_without_cost', 'information_ratio'), 'risk'],
        '信息比率<br>(含成本)': analysis_df.loc[('excess_return_with_cost', 'information_ratio'), 'risk'],
    }
    colors = ['#2ecc71', '#27ae60', '#3498db', '#2980b9']
    fig.add_trace(
        go.Bar(x=list(metrics.keys()), y=list(metrics.values()),
               marker_color=colors,
               text=[f'{v:.3f}' for v in metrics.values()],
               textposition='outside'),
        row=3, col=3
    )

    # 更新布局
    fig.update_layout(
        title_text="Qlib量化策略回测分析报告 (交互式)",
        title_font_size=20,
        showlegend=True,
        height=1200,
        hovermode='x unified'
    )

    # 更新坐标轴
    fig.update_xaxes(title_text="日期", row=1, col=1)
    fig.update_xaxes(title_text="IC值", row=1, col=2)
    fig.update_xaxes(title_text="日期", row=1, col=3)
    fig.update_xaxes(title_text="日期", row=2, col=1)
    fig.update_xaxes(title_text="日期", row=2, col=2)
    fig.update_xaxes(title_text="日期", row=2, col=3)
    fig.update_xaxes(title_text="预测分数", row=3, col=1)
    fig.update_xaxes(title_text="日期", row=3, col=2)

    fig.update_yaxes(title_text="IC值", row=1, col=1)
    fig.update_yaxes(title_text="频数", row=1, col=2)
    fig.update_yaxes(title_text="累积收益", row=1, col=3)
    fig.update_yaxes(title_text="累积超额收益", row=2, col=1)
    fig.update_yaxes(title_text="累积超额收益", row=2, col=2)
    fig.update_yaxes(title_text="回撤幅度", row=2, col=3)
    fig.update_yaxes(title_text="频数", row=3, col=1)
    fig.update_yaxes(title_text="换手率", row=3, col=2)
    fig.update_yaxes(title_text="数值", row=3, col=3)

    # 保存为HTML
    fig.write_html(output_file)
    print(f"[OK] 交互式HTML报告已生成: {output_file}")
    print(f"   包含9个交互式图表:")
    print(f"   - 可以缩放、平移、查看详细数据")
    print(f"   - 鼠标悬停显示数值")
    print(f"   - 可以隐藏/显示图例")

    # 生成指标摘要HTML
    summary_html = f"""
    <div style="margin: 20px; padding: 20px; background: #f5f5f5; border-radius: 10px;">
        <h2 style="color: #2c3e50;">📊 回测结果摘要</h2>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px;">
            <div style="background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h3 style="color: #27ae60; margin: 0;">💰 超额收益 (无成本)</h3>
                <p><strong>年化收益率:</strong> {analysis_df.loc[('excess_return_without_cost', 'annualized_return'), 'risk']:.2%}</p>
                <p><strong>信息比率:</strong> {analysis_df.loc[('excess_return_without_cost', 'information_ratio'), 'risk']:.4f}</p>
                <p><strong>最大回撤:</strong> {analysis_df.loc[('excess_return_without_cost', 'max_drawdown'), 'risk']:.2%}</p>
            </div>
            <div style="background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h3 style="color: #e67e22; margin: 0;">💸 超额收益 (含成本)</h3>
                <p><strong>年化收益率:</strong> {analysis_df.loc[('excess_return_with_cost', 'annualized_return'), 'risk']:.2%}</p>
                <p><strong>信息比率:</strong> {analysis_df.loc[('excess_return_with_cost', 'information_ratio'), 'risk']:.4f}</p>
                <p><strong>最大回撤:</strong> {analysis_df.loc[('excess_return_with_cost', 'max_drawdown'), 'risk']:.2%}</p>
            </div>
        </div>
        <div style="margin-top: 20px; padding: 15px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <h3 style="color: #3498db; margin: 0;">📈 因子质量</h3>
            <p><strong>平均IC:</strong> {ic_series.mean():.4f}</p>
            <p><strong>IC标准差:</strong> {ic_series.std():.4f}</p>
            <p><strong>IC>0占比:</strong> {(ic_series > 0).sum() / len(ic_series):.2%}</p>
        </div>
    </div>
    """

    # 插入摘要到HTML
    with open(output_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    html_content = html_content.replace('</body>', f'{summary_html}</body>')

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    # 自动打开浏览器
    if auto_open:
        import webbrowser
        webbrowser.open(f'file://{Path(output_file).absolute()}')
        print(f"\n[OK] 已在浏览器中打开报告")

    return output_file

if __name__ == "__main__":
    import sys

    output_file = "backtest_report.html"
    auto_open = True

    if len(sys.argv) > 1:
        output_file = sys.argv[1]
    if len(sys.argv) > 2:
        auto_open = sys.argv[2].lower() in ['true', '1', 'yes']

    print("正在生成交互式HTML报告...\n")
    create_html_report(output_file, auto_open)
