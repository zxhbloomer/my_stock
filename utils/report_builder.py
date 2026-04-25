# utils/report_builder.py
"""
通用回测报告构建器
支持链式调用，生成中文 Plotly HTML 报告
"""
import os
from datetime import datetime
import plotly.graph_objects as go
from plotly.offline import plot as plotly_plot


class BacktestReportBuilder:
    """
    通用 HTML 回测报告构建器，支持链式调用。

    用法：
        builder = BacktestReportBuilder("BBI策略回测", "2025-04-01 ~ 2026-03-20")
        builder.add_metrics([{"label": "总收益", "value": "13.1%", "is_positive": True}])
        builder.add_chart(fig, "累计收益曲线")
        builder.save("reports/report.html")
    """

    def __init__(self, title: str, subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle
        self._metrics: list[dict] = []
        self._charts: list[tuple[go.Figure, str]] = []

    def add_metrics(self, metrics: list[dict]) -> "BacktestReportBuilder":
        """添加指标卡。metrics: [{"label": str, "value": str, "is_positive": bool}]"""
        self._metrics = metrics
        return self

    def add_chart(self, fig: go.Figure, chart_title: str = "") -> "BacktestReportBuilder":
        """添加图表。"""
        self._charts.append((fig, chart_title))
        return self

    def save(self, output_path: str) -> str:
        """保存 HTML 报告，返回文件路径。"""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        html = self._build_html()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path

    def _metric_card_html(self, m: dict) -> str:
        color = "#28a745" if m.get("is_positive") else "#dc3545"
        return (
            f'<div class="metric-card">'
            f'<div class="metric-value" style="color:{color}">{m["value"]}</div>'
            f'<div class="metric-label">{m["label"]}</div>'
            f'</div>'
        )

    def _chart_html(self, fig: go.Figure, chart_title: str) -> str:
        # 保留图表自身设置的 height（subplots 图表需要足够高度才能正常渲染）
        current_height = fig.layout.height
        update = dict(margin=dict(l=10, r=10, t=40, b=10))
        if current_height:
            update["height"] = current_height
        fig.update_layout(**update)
        # subplots 图表（有 height 设置）用内嵌 plotlyjs，避免 CDN 加载时序问题导致 Candlestick 不渲染
        include_js = "cdn" if not current_height else True
        div = plotly_plot(fig, include_plotlyjs=include_js, output_type="div")
        return (
            f'<div class="chart-card">'
            f'<div class="chart-header"><h3 class="chart-title">{chart_title}</h3></div>'
            f'<div class="chart-body">{div}</div>'
            f'</div>'
        )

    def _build_html(self) -> str:
        metrics_html = "".join(self._metric_card_html(m) for m in self._metrics)
        charts_html = "".join(self._chart_html(f, t) for f, t in self._charts)
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self.title}</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root {{
    --bg: #ffffff; --bg2: #f8f9fa; --border: #dee2e6;
    --text: #212529; --text2: #6c757d;
    --shadow: 0 2px 4px rgba(0,0,0,0.1);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,'Microsoft YaHei',sans-serif; }}
.container {{ max-width:96%; margin:0 auto; padding:0 1rem; }}
.header {{ background:var(--bg2); border-bottom:1px solid var(--border); padding:1.5rem 0; margin-bottom:1.5rem; }}
.header-title {{ font-size:1.8rem; font-weight:700; margin-bottom:0.3rem; }}
.header-subtitle {{ color:var(--text2); font-size:0.9rem; }}
.metrics-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:1rem; margin-bottom:1.5rem; }}
.metric-card {{ background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:1rem; text-align:center; box-shadow:var(--shadow); transition:all 0.2s; }}
.metric-card:hover {{ transform:translateY(-3px); box-shadow:0 4px 12px rgba(0,0,0,0.15); }}
.metric-value {{ font-size:1.6rem; font-weight:700; margin-bottom:0.2rem; }}
.metric-label {{ font-size:0.75rem; color:var(--text2); letter-spacing:0.5px; }}
.chart-card {{ background:var(--bg); border:1px solid var(--border); border-radius:10px; overflow:hidden; box-shadow:var(--shadow); margin-bottom:1.5rem; }}
.chart-header {{ background:var(--bg2); padding:0.8rem 1.2rem; border-bottom:1px solid var(--border); }}
.chart-title {{ font-size:1.1rem; font-weight:600; margin:0; }}
.chart-body {{ padding:0; width:100%; }}
.footer {{ text-align:center; color:var(--text2); font-size:0.8rem; padding:1.5rem 0; border-top:1px solid var(--border); margin-top:1rem; }}
</style>
</head>
<body>
<div class="header">
  <div class="container">
    <div class="header-title">{self.title}</div>
    <div class="header-subtitle">{self.subtitle}</div>
  </div>
</div>
<div class="container">
  <div class="metrics-grid">{metrics_html}</div>
  {charts_html}
</div>
<div class="footer">生成时间：{generated}</div>
</body>
</html>"""
