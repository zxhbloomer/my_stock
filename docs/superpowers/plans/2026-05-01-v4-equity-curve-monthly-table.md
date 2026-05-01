# v4_plan 资金曲线 + 月度收益表格 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v4_plan 的 HTML 报表第二个 section 新增"资金曲线（绝对金额）+ 月度收益表格"，不改动现有任何 Figure。

**Architecture:** 在 `30_generate_report.py` 新增独立函数 `make_equity_figure(nav_df)`，用 `make_subplots` 左右分栏（60/40），左侧 `go.Scatter` 画绝对资金曲线，右侧 `go.Table` 显示月度收益明细（5列，带颜色和箭头）。在 `make_html()` 中将新 Figure 插入 section 列表第二位。

**Tech Stack:** Python 3.11, Plotly `go.Figure` / `make_subplots`, Pandas resample

---

## 文件变更清单

| 操作 | 文件 |
|------|------|
| Modify | `scripts/bbi/backtrader/v4_plan/30_generate_report.py` |

只改一个文件，新增一个函数，修改 `make_html()` 的 section 列表。

---

### Task 1: 新增 `make_equity_figure(nav_df)` 函数

**Files:**
- Modify: `scripts/bbi/backtrader/v4_plan/30_generate_report.py`

- [ ] **Step 1: 在文件顶部确认 `make_subplots` 已导入**

打开 `30_generate_report.py`，第 6 行已有：
```python
from plotly.subplots import make_subplots
```
如果没有，加上。已有则跳过。

- [ ] **Step 2: 在 `make_html()` 函数之前插入 `make_equity_figure` 函数**

在 `30_generate_report.py` 的 `# ══════════════════════════════════════════════════════════` 分隔线（`# 4. HTML 报表生成` 之前）插入以下完整函数：

```python
# ══════════════════════════════════════════════════════════
# 3b. 资金曲线 + 月度收益表格
# ══════════════════════════════════════════════════════════

def make_equity_figure(nav_df):
    # ── 月度数据计算 ──────────────────────────────────────
    nav_indexed = nav_df.set_index('date')
    monthly_nav = nav_indexed['nav'].resample('ME').last()
    monthly_pnl = monthly_nav.diff()
    monthly_ret = nav_indexed['pct_chg'].resample('ME').apply(
        lambda x: (1 + x).prod() - 1
    )
    cumulative_ret = monthly_nav / INIT_CASH - 1

    # ── 辅助：格式化带箭头的数值 ──────────────────────────
    def fmt_arrow(val, is_pct=False, is_currency=False):
        if val != val:  # NaN
            return '-'
        if is_pct:
            s = f'{val * 100:.2f}%'
        elif is_currency:
            s = f'{val:,.0f}'
        else:
            s = f'{val:.2f}'
        if val > 0:
            return f'▲ +{s}'
        elif val < 0:
            return f'▼ {s}'
        else:
            return s

    def cell_color(val):
        if val != val or val == 0:
            return '#f5f5f5'
        return '#d4edda' if val > 0 else '#f8d7da'

    # ── 构建表格行数据 ────────────────────────────────────
    months      = [d.strftime('%Y-%m') for d in monthly_nav.index]
    nav_vals    = [f'{v:,.0f} 元' for v in monthly_nav.values]
    pnl_vals    = [fmt_arrow(v, is_currency=True) for v in monthly_pnl.values]
    ret_vals    = [fmt_arrow(v, is_pct=True) for v in monthly_ret.values]
    cum_vals    = [fmt_arrow(v, is_pct=True) for v in cumulative_ret.values]

    pnl_colors  = [cell_color(v) for v in monthly_pnl.values]
    ret_colors  = [cell_color(v) for v in monthly_ret.values]
    cum_colors  = [cell_color(v) for v in cumulative_ret.values]
    nav_colors  = ['#ffffff'] * len(months)
    mon_colors  = ['#f0f4f8'] * len(months)

    # ── Figure：左资金曲线 + 右月度表格 ──────────────────
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.60, 0.40],
        specs=[[{'type': 'xy'}, {'type': 'table'}]],
    )

    # 左：资金曲线（绝对金额）
    fig.add_trace(
        go.Scatter(
            x=nav_df['date'],
            y=nav_df['nav'],
            name='资金（元）',
            line=dict(color='#2196F3', width=2),
        ),
        row=1, col=1,
    )

    # 右：月度收益表格
    fig.add_trace(
        go.Table(
            header=dict(
                values=['年月', '月末总资产', '当月盈亏额', '当月收益率', '累计收益率'],
                fill_color='#2c3e50',
                font=dict(color='white', size=12),
                align='center',
            ),
            cells=dict(
                values=[months, nav_vals, pnl_vals, ret_vals, cum_vals],
                fill_color=[mon_colors, nav_colors, pnl_colors, ret_colors, cum_colors],
                align='center',
                font=dict(size=12),
            ),
        ),
        row=1, col=2,
    )

    fig.update_layout(
        template='none',
        width=1500,
        height=max(500, min(900, len(months) * 28 + 80)),
        title=dict(text='资金曲线 & 月度收益明细', x=0.02, xanchor='left'),
        yaxis=dict(title='资金（元）', tickformat=',.0f'),
        margin=dict(t=60, b=40),
        showlegend=False,
    )
    return fig
```

- [ ] **Step 3: 在 `make_html()` 中插入新 Figure 为第二个 section**

找到 `make_html()` 函数内的这段代码（约第 137 行附近）：

```python
section_labels = ['净值曲线', '年度收益', '下周操作计划', '持仓周报（最近10周）', '历史交易明细']
sections_html = ''
for i, (fig, label) in enumerate(zip([fig1, fig2, fig3, fig4, fig5], section_labels), 1):
```

修改为：

```python
fig_equity = make_equity_figure(nav_df)

section_labels = ['净值曲线', '资金曲线 & 月度收益', '年度收益', '下周操作计划', '持仓周报（最近10周）', '历史交易明细']
sections_html = ''
for i, (fig, label) in enumerate(zip([fig1, fig_equity, fig2, fig3, fig4, fig5], section_labels), 1):
```

注意：`fig_equity = make_equity_figure(nav_df)` 这行要放在 `section_labels = ...` 之前，且 `nav_df` 已经是 `make_html()` 的参数，直接可用。

---

### Task 2: 验证运行

**Files:**
- Run: `scripts/bbi/backtrader/v4_plan/30_generate_report.py`

- [ ] **Step 1: 确认 output 目录有回测结果**

```bash
ls scripts/bbi/backtrader/v4_plan/output/
```

预期看到：`nav_series.csv`, `weekly_records.json`, `trade_records.csv`, `last_holdings.json`

- [ ] **Step 2: 运行报表生成脚本**

```bash
cd D:\2026_project\10_quantify\00_py\my_stock
python -X utf8 scripts/bbi/backtrader/v4_plan/30_generate_report.py
```

预期输出：
```
Report saved: scripts\bbi\backtrader\v4_plan\output\report.html
Done! Opening: ...
```
无报错，浏览器自动打开。

- [ ] **Step 3: 在浏览器中验证**

检查项：
1. 第二个 section 标题为"资金曲线 & 月度收益"
2. 左侧曲线 Y 轴显示元（如 `500,000`），从初始资金附近起步
3. 右侧表格有 5 列：年月、月末总资产、当月盈亏额、当月收益率、累计收益率
4. 正收益行背景绿色 + `▲`，负收益行背景红色 + `▼`
5. 原有其他 5 个 section 内容不变

---

## 自检清单

- [x] spec 中"资金曲线绝对金额"→ Task 1 Step 2 `go.Scatter` y=`nav_df['nav']`
- [x] spec 中"月度收益表格 5 列"→ Task 1 Step 2 `go.Table` 5列定义
- [x] spec 中"颜色规则绿/红/灰"→ `cell_color()` 函数
- [x] spec 中"箭头 ▲/▼"→ `fmt_arrow()` 函数
- [x] spec 中"插入第二位"→ Task 1 Step 3 section 列表
- [x] spec 中"不引入新依赖"→ 纯 Plotly + Pandas
- [x] spec 中"不修改现有 Figure"→ 只在 `make_html()` 末尾追加，不动 fig1-fig5
