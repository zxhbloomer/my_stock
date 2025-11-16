"""
滚动窗口验证可视化脚本 - 从MLflow加载数据生成完整的HTML报告（使用Plotly解决中文字体问题）

功能:
1. 从MLflow加载所有滚动验证结果
2. 生成4张专业图表（使用Plotly，无字体问题）
3. 保存为交互式HTML报告

使用方法:
    python scripts/result/滚动验证可视化.py
    python scripts/result/滚动验证可视化.py --experiment rolling_validation
    python scripts/result/滚动验证可视化.py --no-open

作者: AI Assistant
日期: 2025-11-16
"""
import sys
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
import qlib
from qlib.workflow import R
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class RollingValidationVisualizer:
    """滚动窗口验证可视化器 - 从MLflow加载数据"""

    def __init__(self, experiment_name="rolling_validation"):
        """
        初始化可视化器

        参数:
            experiment_name: MLflow实验名称
        """
        self.experiment_name = experiment_name
        self.output_dir = Path("validation_results/charts")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 从MLflow加载所有结果
        self.df = self._load_from_mlflow()
        print(f"✅ 从MLflow加载结果: {len(self.df)} 个测试期")

    def _load_from_mlflow(self):
        """从MLflow加载所有滚动验证结果"""
        print(f"\n🔍 正在从MLflow实验 '{self.experiment_name}' 加载数据...")

        try:
            # R.list_recorders返回字典: {recorder_id: MLflowRecorder对象}
            recorders_dict = R.list_recorders(experiment_name=self.experiment_name)

            if not recorders_dict:
                raise ValueError(f"实验 '{self.experiment_name}' 中没有记录。\n"
                               f"提示: 请先运行 scripts/50_滚动窗口验证.py")

            print(f"找到 {len(recorders_dict)} 个recorder记录")

            # 从每个recorder加载数据
            results = []
            for recorder_id, recorder in recorders_dict.items():
                try:
                    # 加载参数
                    params = recorder.list_params()

                    # 加载指标
                    metrics = recorder.list_metrics()

                    # 检查是否包含IC指标（过滤掉非滚动验证的recorder）
                    if 'ic_mean' not in metrics:
                        print(f"  ⚠️ 跳过 {params.get('period_name', 'Unknown')}: 缺少IC指标")
                        continue

                    # 组合结果
                    result = {
                        'recorder_id': recorder_id,
                        'period': params.get('period_name', 'Unknown'),
                        'test_start': params.get('test_start', ''),
                        'test_end': params.get('test_end', ''),
                        'train_start': params.get('train_start', ''),
                        'train_end': params.get('train_end', ''),
                        'valid_start': params.get('valid_start', ''),
                        'valid_end': params.get('valid_end', ''),
                        'ic_mean': metrics.get('ic_mean', 0),
                        'ic_std': metrics.get('ic_std', 0),
                        'ic_ir': metrics.get('ic_ir', 0),
                        'ic_positive_ratio': metrics.get('ic_positive_ratio', 0),
                        'sample_days': int(metrics.get('sample_days', 0)),
                        'start_time': recorder.start_time  # 用于去重
                    }
                    results.append(result)

                except Exception as e:
                    print(f"  ⚠️ 跳过recorder {recorder_id}: {str(e)}")
                    continue

            if not results:
                raise ValueError("没有成功加载任何包含IC指标的结果。\n"
                               "提示: 请检查滚动窗口验证脚本是否正确保存了IC指标。")

            # 转换为DataFrame
            df = pd.DataFrame(results)

            # 去重：同一测试期只保留最新的记录
            df = df.sort_values('start_time', ascending=False)  # 最新的在前
            df = df.drop_duplicates(subset=['period'], keep='first')  # 保留每个period的第一条（最新）
            df = df.sort_values('test_start').reset_index(drop=True)  # 按测试日期排序

            # 删除临时列
            df = df.drop(columns=['start_time'])

            print(f"\n去重后保留 {len(df)} 个测试期")
            for _, row in df.iterrows():
                print(f"  ✅ {row['period']}: IC={row['ic_mean']:.4f}")

            return df

        except Exception as e:
            print(f"❌ 从MLflow加载失败: {str(e)}")
            print("提示: 请确保已运行滚动窗口验证脚本并保存结果到MLflow")
            import traceback
            traceback.print_exc()
            raise

    def plot_ic_timeseries(self):
        """绘制图1: IC时序图 (IC均值 + IC_IR)"""
        print("  生成图表1: IC时序图...")

        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=('IC均值时序图', 'IC_IR (信息比率) 时序图'),
            vertical_spacing=0.12
        )

        periods = self.df['period'].values
        ic_mean = self.df['ic_mean'].values
        ic_ir = self.df['ic_ir'].values

        # 子图1: IC均值
        fig.add_trace(
            go.Scatter(
                x=periods, y=ic_mean,
                mode='lines+markers',
                name='IC均值',
                line=dict(color='#3498db', width=3),
                marker=dict(size=10),
                hovertemplate='<b>%{x}</b><br>IC均值: %{y:.4f}<extra></extra>'
            ),
            row=1, col=1
        )
        fig.add_hline(y=0.03, line_dash="dash", line_color="green",
                     annotation_text="优秀(0.03)", row=1, col=1)
        fig.add_hline(y=0.01, line_dash="dash", line_color="orange",
                     annotation_text="可接受(0.01)", row=1, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="red", row=1, col=1)

        # 子图2: IC_IR
        fig.add_trace(
            go.Scatter(
                x=periods, y=ic_ir,
                mode='lines+markers',
                name='IC_IR',
                line=dict(color='#e74c3c', width=3),
                marker=dict(size=10),
                hovertemplate='<b>%{x}</b><br>IC_IR: %{y:.4f}<extra></extra>'
            ),
            row=2, col=1
        )
        fig.add_hline(y=1.0, line_dash="dash", line_color="green",
                     annotation_text="优秀(1.0)", row=2, col=1)
        fig.add_hline(y=0.5, line_dash="dash", line_color="orange",
                     annotation_text="可接受(0.5)", row=2, col=1)

        fig.update_xaxes(title_text="测试期", row=1, col=1)
        fig.update_xaxes(title_text="测试期", row=2, col=1)
        fig.update_yaxes(title_text="IC均值", row=1, col=1)
        fig.update_yaxes(title_text="IC_IR", row=2, col=1)

        fig.update_layout(
            title_text="滚动窗口验证 - IC时序分析",
            height=800,
            showlegend=True,
            hovermode='x unified',
            template='plotly_white'
        )

        return fig

    def plot_ic_distribution(self):
        """绘制图2: IC分布图 (小提琴图 + IC标准差柱状图)"""
        print("  生成图表2: IC分布图...")

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('IC均值分布 (小提琴图)', 'IC标准差 (波动性)'),
            horizontal_spacing=0.15
        )

        periods = self.df['period'].values
        ic_mean = self.df['ic_mean'].values
        ic_std = self.df['ic_std'].values

        # 子图1: IC均值小提琴图
        fig.add_trace(
            go.Violin(
                y=ic_mean,
                name='IC均值分布',
                box_visible=True,
                meanline_visible=True,
                fillcolor='#3498db',
                opacity=0.6,
                x0='IC分布'
            ),
            row=1, col=1
        )

        # 子图2: IC标准差柱状图
        colors = ['#27ae60' if x < 0.05 else '#f39c12' if x < 0.10 else '#e74c3c'
                  for x in ic_std]
        fig.add_trace(
            go.Bar(
                x=periods, y=ic_std,
                name='IC标准差',
                marker_color=colors,
                hovertemplate='<b>%{x}</b><br>IC标准差: %{y:.4f}<extra></extra>'
            ),
            row=1, col=2
        )
        fig.add_hline(y=0.05, line_dash="dash", line_color="green",
                     annotation_text="优秀(<0.05)", row=1, col=2)
        fig.add_hline(y=0.10, line_dash="dash", line_color="orange",
                     annotation_text="可接受(<0.10)", row=1, col=2)

        fig.update_xaxes(title_text="", row=1, col=1)
        fig.update_xaxes(title_text="测试期", row=1, col=2)
        fig.update_yaxes(title_text="IC均值", row=1, col=1)
        fig.update_yaxes(title_text="IC标准差", row=1, col=2)

        fig.update_layout(
            title_text="滚动窗口验证 - IC分布与波动性分析",
            height=500,
            showlegend=False,
            template='plotly_white'
        )

        return fig

    def plot_stability_analysis(self):
        """绘制图3: 稳定性分析 (4个子图)"""
        print("  生成图表3: 稳定性分析...")

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                'IC正值占比 (预测准确率)',
                '有效交易日数 (数据覆盖度)',
                '风险-收益散点图 (IC_IR vs IC均值)',
                '策略衰减趋势分析'
            ),
            specs=[
                [{"type": "bar"}, {"type": "bar"}],
                [{"type": "scatter"}, {"type": "scatter"}]
            ],
            vertical_spacing=0.15,
            horizontal_spacing=0.12
        )

        periods = self.df['period'].values
        ic_mean = self.df['ic_mean'].values
        ic_std = self.df['ic_std'].values
        ic_ir = self.df['ic_ir'].values
        ic_pos_ratio = self.df['ic_positive_ratio'].values
        sample_days = self.df['sample_days'].values

        # 子图1: IC正值占比
        colors1 = ['#27ae60' if x > 0.7 else '#f39c12' if x > 0.55 else '#e74c3c'
                   for x in ic_pos_ratio]
        fig.add_trace(
            go.Bar(
                x=periods, y=ic_pos_ratio * 100,
                marker_color=colors1,
                name='IC正值占比',
                hovertemplate='<b>%{x}</b><br>IC正值占比: %{y:.1f}%<extra></extra>'
            ),
            row=1, col=1
        )
        fig.add_hline(y=70, line_dash="dash", line_color="green",
                     annotation_text="优秀(70%)", row=1, col=1)
        fig.add_hline(y=55, line_dash="dash", line_color="orange",
                     annotation_text="可接受(55%)", row=1, col=1)

        # 子图2: 有效交易日数
        fig.add_trace(
            go.Bar(
                x=periods, y=sample_days,
                marker_color='#9b59b6',
                name='有效天数',
                hovertemplate='<b>%{x}</b><br>有效交易日: %{y}天<extra></extra>'
            ),
            row=1, col=2
        )

        # 子图3: 风险-收益散点图
        fig.add_trace(
            go.Scatter(
                x=ic_mean, y=ic_ir,
                mode='markers+text',
                marker=dict(size=15, color='#3498db', opacity=0.6),
                text=periods,
                textposition='top center',
                name='测试期',
                hovertemplate='<b>%{text}</b><br>IC均值: %{x:.4f}<br>IC_IR: %{y:.4f}<extra></extra>'
            ),
            row=2, col=1
        )
        # 添加象限线
        fig.add_vline(x=0.03, line_dash="dash", line_color="green", row=2, col=1)
        fig.add_hline(y=1.0, line_dash="dash", line_color="green", row=2, col=1)

        # 子图4: 策略衰减趋势（线性拟合）
        test_indices = np.arange(len(ic_mean))
        z = np.polyfit(test_indices, ic_mean, 1)
        p = np.poly1d(z)
        trend_line = p(test_indices)

        fig.add_trace(
            go.Scatter(
                x=periods, y=ic_mean,
                mode='markers',
                marker=dict(size=10, color='#3498db'),
                name='实际IC',
                hovertemplate='<b>%{x}</b><br>IC均值: %{y:.4f}<extra></extra>'
            ),
            row=2, col=2
        )
        fig.add_trace(
            go.Scatter(
                x=periods, y=trend_line,
                mode='lines',
                line=dict(color='#e74c3c', width=3, dash='dash'),
                name=f'趋势线 (斜率={z[0]:.5f})',
                hovertemplate='趋势线<extra></extra>'
            ),
            row=2, col=2
        )

        # 更新坐标轴
        fig.update_xaxes(title_text="测试期", row=1, col=1)
        fig.update_xaxes(title_text="测试期", row=1, col=2)
        fig.update_xaxes(title_text="IC均值", row=2, col=1)
        fig.update_xaxes(title_text="测试期", row=2, col=2)

        fig.update_yaxes(title_text="占比 (%)", row=1, col=1)
        fig.update_yaxes(title_text="天数", row=1, col=2)
        fig.update_yaxes(title_text="IC_IR", row=2, col=1)
        fig.update_yaxes(title_text="IC均值", row=2, col=2)

        fig.update_layout(
            title_text="滚动窗口验证 - 稳定性与衰减分析",
            height=900,
            showlegend=True,
            template='plotly_white'
        )

        return fig

    def plot_performance_heatmap(self):
        """绘制图4: 性能热力图 (多指标综合对比)"""
        print("  生成图表4: 性能热力图...")

        # 准备热力图数据
        metrics_names = ['IC均值', 'IC_IR', 'IC正值占比', 'IC稳定性', '有效天数']
        periods = self.df['period'].values

        # 归一化各指标到0-100分
        ic_mean_score = (self.df['ic_mean'].values / 0.10) * 100  # 0.10为满分
        ic_ir_score = (self.df['ic_ir'].values / 2.0) * 100  # 2.0为满分
        ic_pos_score = self.df['ic_positive_ratio'].values * 100  # 已是百分比
        ic_stable_score = (1 - self.df['ic_std'].values / 0.20) * 100  # IC_std越小越好
        sample_score = (self.df['sample_days'].values / 250) * 100  # 250天为满分

        # 限制在0-100范围
        ic_mean_score = np.clip(ic_mean_score, 0, 100)
        ic_ir_score = np.clip(ic_ir_score, 0, 100)
        ic_stable_score = np.clip(ic_stable_score, 0, 100)
        sample_score = np.clip(sample_score, 0, 100)

        # 组合数据矩阵
        z_data = np.array([
            ic_mean_score,
            ic_ir_score,
            ic_pos_score,
            ic_stable_score,
            sample_score
        ])

        # 创建热力图
        fig = go.Figure(data=go.Heatmap(
            z=z_data,
            x=periods,
            y=metrics_names,
            colorscale='RdYlGn',  # 红-黄-绿配色
            text=np.round(z_data, 1),
            texttemplate='%{text}',
            textfont={"size": 10},
            colorbar=dict(title="评分"),
            hovertemplate='<b>%{y}</b><br>测试期: %{x}<br>评分: %{z:.1f}<extra></extra>'
        ))

        fig.update_layout(
            title_text="滚动窗口验证 - 性能热力图 (多指标综合评分)",
            xaxis_title="测试期",
            yaxis_title="评价指标",
            height=500,
            template='plotly_white'
        )

        return fig

    def generate_all_charts(self):
        """生成所有图表并保存为HTML文件"""
        print("\n📊 正在生成所有图表...")

        # 删除旧的图表文件（如果存在）
        for old_file in self.output_dir.glob("*.html"):
            if old_file.name.startswith(('01_', '02_', '03_', '04_')):
                old_file.unlink()
                print(f"  删除旧文件: {old_file.name}")

        chart_files = []

        # 图1: IC时序图
        fig1 = self.plot_ic_timeseries()
        path1 = self.output_dir / "01_ic_timeseries.html"
        fig1.write_html(path1)
        chart_files.append(path1)

        # 图2: IC分布图
        fig2 = self.plot_ic_distribution()
        path2 = self.output_dir / "02_ic_distribution.html"
        fig2.write_html(path2)
        chart_files.append(path2)

        # 图3: 稳定性分析
        fig3 = self.plot_stability_analysis()
        path3 = self.output_dir / "03_stability_analysis.html"
        fig3.write_html(path3)
        chart_files.append(path3)

        # 图4: 性能热力图
        fig4 = self.plot_performance_heatmap()
        path4 = self.output_dir / "04_performance_heatmap.html"
        fig4.write_html(path4)
        chart_files.append(path4)

        print(f"✅ 所有图表已生成: {len(chart_files)} 个文件")

        return chart_files, [fig1, fig2, fig3, fig4]

    def generate_html_report(self, chart_files, figs):
        """生成包含所有图表的完整HTML报告"""
        print("\n📝 正在生成HTML报告...")

        # 计算汇总统计
        avg_ic = self.df['ic_mean'].mean()
        avg_ir = self.df['ic_ir'].mean()
        ic_above_003 = (self.df['ic_mean'] > 0.03).mean()
        ic_positive = self.df['ic_positive_ratio'].mean()

        # 生成建议
        recommendation = self._generate_recommendation()

        # 生成数据表格
        table_html = self._generate_data_table()

        # 将4个图表嵌入HTML
        chart_htmls = []
        for fig in figs:
            chart_html = fig.to_html(include_plotlyjs='cdn', full_html=False, div_id=None)
            chart_htmls.append(chart_html)

        # 完整HTML
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>滚动窗口验证报告 - {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}

        .card {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.3s;
        }}

        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.15);
        }}

        .card-title {{
            font-size: 0.9em;
            color: #6c757d;
            margin-bottom: 10px;
        }}

        .card-value {{
            font-size: 2em;
            font-weight: bold;
            color: #2c3e50;
        }}

        .card-value.green {{
            color: #27ae60;
        }}

        .card-value.red {{
            color: #e74c3c;
        }}

        .section {{
            padding: 30px;
        }}

        .section-title {{
            font-size: 1.8em;
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}

        .chart-container {{
            margin-bottom: 40px;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
        }}

        .recommendation {{
            background: #fff3cd;
            border-left: 5px solid #ffc107;
            padding: 20px;
            margin: 20px 0;
            border-radius: 5px;
        }}

        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}

        .data-table th, .data-table td {{
            padding: 12px;
            text-align: center;
            border: 1px solid #dee2e6;
        }}

        .data-table th {{
            background: #667eea;
            color: white;
            font-weight: bold;
        }}

        .data-table tr:nth-child(even) {{
            background: #f8f9fa;
        }}

        .data-table tr:hover {{
            background: #e9ecef;
        }}

        .footer {{
            background: #2c3e50;
            color: white;
            padding: 20px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 滚动窗口验证报告</h1>
            <p>量化策略稳健性评估 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="summary-cards">
            <div class="card">
                <div class="card-title">测试期数</div>
                <div class="card-value">{len(self.df)}</div>
            </div>
            <div class="card">
                <div class="card-title">平均IC均值</div>
                <div class="card-value {'green' if avg_ic > 0.03 else 'red' if avg_ic < 0.01 else ''}">{avg_ic:.4f}</div>
            </div>
            <div class="card">
                <div class="card-title">平均IC_IR</div>
                <div class="card-value {'green' if avg_ir > 1.0 else 'red' if avg_ir < 0.5 else ''}">{avg_ir:.4f}</div>
            </div>
            <div class="card">
                <div class="card-title">IC>0.03占比</div>
                <div class="card-value {'green' if ic_above_003 > 0.7 else 'red' if ic_above_003 < 0.5 else ''}">{ic_above_003:.1%}</div>
            </div>
            <div class="card">
                <div class="card-title">IC正值占比</div>
                <div class="card-value {'green' if ic_positive > 0.7 else 'red' if ic_positive < 0.55 else ''}">{ic_positive:.1%}</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">📈 图表1: IC时序分析</h2>
            <div class="chart-container">
                {chart_htmls[0]}
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">📊 图表2: IC分布与波动性</h2>
            <div class="chart-container">
                {chart_htmls[1]}
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">🔍 图表3: 稳定性与衰减分析</h2>
            <div class="chart-container">
                {chart_htmls[2]}
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">🌡️ 图表4: 性能热力图</h2>
            <div class="chart-container">
                {chart_htmls[3]}
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">🎯 实盘建议</h2>
            <div class="recommendation">
                {recommendation}
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">📋 详细数据表</h2>
            {table_html}
        </div>

        <div class="footer">
            <p>📊 基于Qlib框架的滚动窗口验证报告</p>
            <p>💾 数据来源: MLflow实验 '{self.experiment_name}'</p>
            <p>🔧 可通过 <code>mlflow ui</code> 查看原始数据</p>
            <p>📁 独立图表文件: {', '.join([f.name for f in chart_files])}</p>
        </div>
    </div>
</body>
</html>"""

        # 保存HTML
        html_path = self.output_dir / "rolling_validation_report.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✅ HTML报告已生成: {html_path}")
        return html_path

    def _generate_recommendation(self):
        """生成实盘建议"""
        avg_ic = self.df['ic_mean'].mean()
        positive_ratio = (self.df['ic_mean'] > 0.03).mean()
        ic_std = self.df['ic_mean'].std()

        # 计算衰减趋势
        test_indices = range(len(self.df))
        ic_mean = self.df['ic_mean'].values
        z = np.polyfit(test_indices, ic_mean, 1)
        decay_slope = z[0]

        recommendation = ""

        # IC表现评估
        if avg_ic > 0.03 and positive_ratio > 0.7:
            recommendation += "✅ <strong>策略表现优秀</strong>,平均IC超过0.03且70%以上测试期表现良好。"
        elif avg_ic > 0.02 and positive_ratio > 0.5:
            recommendation += "⚠️ <strong>策略表现一般</strong>,IC在可接受范围但不够稳定。"
        elif avg_ic > 0.01:
            recommendation += "⚠️ <strong>策略表现较弱</strong>,IC均值偏低且稳定性不足。"
        else:
            recommendation += "❌ <strong>策略已失效</strong>,IC接近零甚至为负,预测能力极弱。"

        # 衰减评估
        if decay_slope < -0.005:
            recommendation += f" 检测到明显的<strong>策略衰减</strong>(衰减率={decay_slope:.4f}),建议使用更近期的数据重新训练。"
        elif decay_slope < -0.002:
            recommendation += f" 存在轻微衰减趋势(衰减率={decay_slope:.4f}),需要持续监控。"

        # 实盘建议
        if avg_ic > 0.03 and positive_ratio > 0.7 and decay_slope > -0.005:
            recommendation += " 可考虑<strong>小资金实盘测试</strong>,建议初始资金不超过总资金的10%,并设置严格的止损。"
        elif avg_ic > 0.02:
            recommendation += " 建议继续优化因子或进行<strong>模拟盘测试</strong>,暂不建议实盘。"
        else:
            recommendation += " <strong>不建议实盘</strong>,需要重新开发策略或更换因子体系。"

        return recommendation

    def _generate_data_table(self):
        """生成数据表格HTML"""
        table_html = '<table class="data-table">\n<thead>\n<tr>\n'

        # 表头
        headers = ['测试期', '测试开始', '测试结束', 'IC均值', 'IC标准差', 'IC_IR', 'IC正值占比', '有效天数', 'Recorder ID']
        for header in headers:
            table_html += f'<th>{header}</th>\n'
        table_html += '</tr>\n</thead>\n<tbody>\n'

        # 数据行
        for _, row in self.df.iterrows():
            table_html += '<tr>\n'
            table_html += f'<td>{row["period"]}</td>\n'
            table_html += f'<td>{row["test_start"]}</td>\n'
            table_html += f'<td>{row["test_end"]}</td>\n'
            table_html += f'<td>{row["ic_mean"]:.4f}</td>\n'
            table_html += f'<td>{row["ic_std"]:.4f}</td>\n'
            table_html += f'<td>{row["ic_ir"]:.4f}</td>\n'
            table_html += f'<td>{row["ic_positive_ratio"]:.2%}</td>\n'
            table_html += f'<td>{int(row["sample_days"])}</td>\n'
            table_html += f'<td style="font-size:0.8em">{row["recorder_id"][:8]}...</td>\n'
            table_html += '</tr>\n'

        table_html += '</tbody>\n</table>'
        return table_html

    def run(self, auto_open=True):
        """运行完整的可视化流程

        参数:
            auto_open: 是否自动打开HTML报告（默认True）
        """
        print(f"\n{'='*80}")
        print(f"滚动窗口验证可视化")
        print(f"{'='*80}\n")

        # 生成所有图表
        chart_files, figs = self.generate_all_charts()

        # 生成HTML报告
        html_path = self.generate_html_report(chart_files, figs)

        print(f"\n{'='*80}")
        print(f"✅ 可视化完成!")
        print(f"{'='*80}")
        print(f"\n📁 输出目录: {self.output_dir}")
        print(f"📊 独立图表: {len(chart_files)} 个HTML文件")
        print(f"📄 完整报告: {html_path}")

        # 自动打开HTML报告
        if auto_open:
            try:
                import webbrowser
                import os

                # 转换为绝对路径
                abs_path = os.path.abspath(html_path)

                print(f"\n🌐 正在浏览器中打开报告...")
                webbrowser.open(f'file:///{abs_path}')
                print(f"✅ 已在默认浏览器中打开报告")

            except Exception as e:
                print(f"\n⚠️ 自动打开浏览器失败: {str(e)}")
                print(f"💡 请手动打开: {html_path}")
        else:
            print(f"\n💡 提示: 在浏览器中打开HTML报告查看完整分析")

        print()  # 空行


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='滚动窗口验证可视化 - 从MLflow加载数据生成交互式图表和报告',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 默认从rolling_validation实验加载并自动打开报告
  python scripts/result/滚动验证可视化.py

  # 指定实验名称
  python scripts/result/滚动验证可视化.py --experiment my_rolling_validation

  # 不自动打开浏览器
  python scripts/result/滚动验证可视化.py --no-open
        """
    )
    parser.add_argument('--experiment', type=str, default='rolling_validation',
                       help='MLflow实验名称(默认: rolling_validation)')
    parser.add_argument('--no-open', action='store_true',
                       help='不自动打开浏览器(默认会自动打开)')

    args = parser.parse_args()

    # 初始化Qlib(需要访问MLflow)
    print("初始化Qlib...")
    qlib.init(provider_uri='D:/Data/my_stock', region='cn')
    print("[OK] Qlib初始化完成\n")

    # 创建可视化器并运行
    visualizer = RollingValidationVisualizer(experiment_name=args.experiment)
    visualizer.run(auto_open=not args.no_open)

    print("\n[OK] 可视化完成!\n")
