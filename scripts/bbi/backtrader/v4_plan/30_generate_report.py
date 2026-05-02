# v4_plan/30_generate_report.py
# BBI 周度轮动策略 — HTML 报表生成，完成后自动打开浏览器
import json
import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import warnings
warnings.filterwarnings('ignore')
from config import (
    START_DATE, END_DATE,
    INIT_CASH, TOP_N,
    RISK_FREE,
    STOCK_DATA_DIR, OUTPUT_DIR,
)


# ══════════════════════════════════════════════════════════
# 1. 加载回测结果
# ══════════════════════════════════════════════════════════

def load_results():
    nav_df = pd.read_csv(OUTPUT_DIR / 'nav_series.csv', parse_dates=['date'])
    nav_df['equity_curve'] = nav_df['nav'] / INIT_CASH
    nav_df['pct_chg'] = nav_df['equity_curve'].pct_change().fillna(0)
    nav_df['max2here'] = nav_df['equity_curve'].expanding().max()
    nav_df['drawdown'] = nav_df['equity_curve'] / nav_df['max2here'] - 1

    with open(OUTPUT_DIR / 'weekly_records.json', encoding='utf-8') as f:
        weekly_records = json.load(f)

    trade_df = pd.read_csv(OUTPUT_DIR / 'trade_records.csv')

    with open(OUTPUT_DIR / 'last_holdings.json', encoding='utf-8') as f:
        last_holdings = set(json.load(f))

    return nav_df, weekly_records, trade_df, last_holdings


# ══════════════════════════════════════════════════════════
# 2. 指标计算
# ══════════════════════════════════════════════════════════

def calc_metrics(nav_df):
    nav = nav_df['equity_curve'].values
    dates = nav_df['date'].values
    total_days = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days
    total_ret = nav[-1] - 1
    annual_ret = (1 + total_ret) ** (365 / total_days) - 1
    max_dd = nav_df['drawdown'].min()

    dd_end = nav_df.loc[nav_df['drawdown'].idxmin(), 'date']
    before_dd = nav_df[nav_df['date'] <= dd_end]
    dd_start = before_dd.loc[before_dd['equity_curve'].idxmax(), 'date'] \
        if len(before_dd) > 0 else dd_end

    daily_ret = nav_df['pct_chg']
    excess = daily_ret - RISK_FREE / 252
    sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0
    calmar = annual_ret / abs(max_dd) if max_dd != 0 else 0

    nav_df2 = nav_df.set_index('date')
    year_ret = nav_df2['pct_chg'].resample('YE').apply(lambda x: (1 + x).prod() - 1)

    end_date = END_DATE or datetime.date.today().strftime("%Y-%m-%d")
    metrics = {
        '累积净值': f'{nav[-1]:.2f}',
        '年化收益': f'{annual_ret*100:.2f}%',
        '最大回撤': f'{max_dd*100:.2f}%',
        '最大回撤开始': str(dd_start)[:10],
        '最大回撤结束': str(dd_end)[:10],
        '夏普比率': f'{sharpe:.3f}',
        '卡玛比率': f'{calmar:.3f}',
        '初始资金': f'{INIT_CASH:,.0f}',
        '最终净值': f'{nav[-1]*INIT_CASH:,.0f}',
        '盈利': f'{(nav[-1]-1)*INIT_CASH:,.0f}',
    }
    return metrics, year_ret, end_date


# ══════════════════════════════════════════════════════════
# 3. 下周操作计划
# ══════════════════════════════════════════════════════════

def get_next_week_plan(last_holdings):
    end_date = END_DATE or datetime.date.today().strftime("%Y-%m-%d")
    frames = []
    for f in STOCK_DATA_DIR.glob('*.parquet'):
        code = f.stem
        if code.startswith('688'):
            continue
        df = pd.read_parquet(f, columns=['trade_date', 'close_qfq', 'bbi_qfq', 'name'])
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df[df['trade_date'] <= end_date].sort_values('trade_date')
        if len(df) < 6:
            continue
        last = df.iloc[-1]
        if last['close_qfq'] <= last['bbi_qfq']:
            continue
        ret5 = df['close_qfq'].iloc[-1] / df['close_qfq'].iloc[-6] - 1 if len(df) >= 6 else 0.0
        frames.append({
            'ts_code': code,
            'name': last['name'],
            'price': round(float(last['close_qfq']), 3),
            'ret5': ret5,
        })

    if not frames:
        return [], []

    df_picks = pd.DataFrame(frames).nlargest(TOP_N, 'ret5')
    buy_plan = []
    for _, row in df_picks.iterrows():
        alloc = INIT_CASH / TOP_N
        shares = int(alloc / row['price'] / 100) * 100
        buy_plan.append({
            'ts_code': row['ts_code'],
            'name': row['name'],
            'ref_price': row['price'],
            'plan_shares': shares,
            'plan_amount': round(row['price'] * shares, 0),
            '5日涨幅': f"{row['ret5']*100:.2f}%",
            '备注': '继续持有' if row['ts_code'] in last_holdings else '新建仓',
        })

    new_set = set(df_picks['ts_code'])
    sell_plan = [c for c in last_holdings if c not in new_set]
    return buy_plan, sell_plan


# ══════════════════════════════════════════════════════════
# 3b. 资金曲线 + 月度收益表格
# ══════════════════════════════════════════════════════════

def make_equity_figure(nav_df):
    # ── 月度数据计算 ──────────────────────────────────────
    nav_indexed = nav_df.set_index('date')
    monthly_nav = nav_indexed['nav'].resample('ME').last()
    monthly_pnl = monthly_nav.diff()
    monthly_pnl.iloc[0] = monthly_nav.iloc[0] - INIT_CASH
    monthly_ret = nav_indexed['pct_chg'].resample('ME').apply(
        lambda x: (1 + x).prod() - 1
    )
    cumulative_ret = monthly_nav / INIT_CASH - 1

    # 年度收益率：每年复利合并
    annual_ret = nav_indexed['pct_chg'].resample('YE').apply(
        lambda x: (1 + x).prod() - 1
    )
    annual_ret_map = {d.year: v for d, v in annual_ret.items()}

    # ── 辅助：格式化带箭头的数值（字体颜色版） ──────────────
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
            return f'+{s} ▲'
        elif val < 0:
            return f'{s} ▼'
        else:
            return s

    def font_color(val):
        if val != val or val == 0:
            return '#333333'
        return '#dc2626' if val > 0 else '#16a34a'  # 红=涨，绿=跌（A股习惯）

    # ── 构建表格列数据 ────────────────────────────────────
    dates       = list(monthly_nav.index)
    n           = len(dates)

    # 年份列：每年只在第一行显示，其余留空；交替背景区分年份块
    # 年份切换的第一行背景色加深，强化视觉分隔
    year_labels = []
    row_bg      = []
    prev_year   = None
    year_toggle = True
    for d in dates:
        yr = d.year
        if yr != prev_year:
            year_labels.append(str(yr))
            prev_year = yr
            year_toggle = not year_toggle
            # 年份切换行背景加深
            row_bg.append('#c8d8e8' if year_toggle else '#e8e8e8')
        else:
            year_labels.append('')
            row_bg.append('#e8f0f8' if year_toggle else '#f8f8f8')

    months_col  = [d.strftime('%m月') for d in dates]
    nav_vals    = [f'{v:,.0f}' for v in monthly_nav.values]
    pnl_vals    = [fmt_arrow(v, is_currency=True) for v in monthly_pnl.values]
    ret_vals    = [fmt_arrow(v, is_pct=True) for v in monthly_ret.values]
    cum_vals    = [fmt_arrow(v, is_pct=True) for v in cumulative_ret.values]

    # 年收益率列：每年最后一个月显示，其余留空
    annual_col  = []
    for i, d in enumerate(dates):
        yr = d.year
        # 判断是否是该年最后一个月（下一行换年或已是最后行）
        is_last_of_year = (i == n - 1) or (dates[i + 1].year != yr)
        if is_last_of_year and yr in annual_ret_map:
            annual_col.append(fmt_arrow(annual_ret_map[yr], is_pct=True))
        else:
            annual_col.append('')

    # 字体颜色列（仅数值列需要红绿）
    pnl_fcolors = [font_color(v) for v in monthly_pnl.values]
    ret_fcolors = [font_color(v) for v in monthly_ret.values]
    cum_fcolors = [font_color(v) for v in cumulative_ret.values]
    ann_fcolors = [font_color(annual_ret_map.get(d.year, float('nan'))
                              if ((i == n-1) or (dates[i+1].year != d.year)) else float('nan'))
                   for i, d in enumerate(dates)]
    neutral     = ['#333333'] * n

    # ── Figure：左右分栏，表格占 50% 保证列宽充足 ────────────
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.50, 0.50],
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

    # 右：月度收益表格（7列）
    # 年份列的竖线颜色与行背景同色 → 边框消失 → 视觉合并效果
    # 其他列统一浅灰竖线
    LIGHT_BORDER = '#d0d7de'
    year_col_line = row_bg  # 年份列每行的线色 = 该行背景色，线消失
    fig.add_trace(
        go.Table(
            columnwidth=[50, 40, 110, 110, 90, 90, 90],
            header=dict(
                values=['年份', '月份', '月末总资产', '当月盈亏(元)', '当月收益率', '累计收益率', '年收益率'],
                fill_color='#2c3e50',
                font=dict(color='white', size=11),
                align='center',
                height=28,
                line_color=LIGHT_BORDER,
            ),
            cells=dict(
                values=[year_labels, months_col, nav_vals, pnl_vals, ret_vals, cum_vals, annual_col],
                fill_color=[row_bg, row_bg, row_bg, row_bg, row_bg, row_bg, row_bg],
                align=['center', 'center', 'right', 'right', 'right', 'right', 'right'],
                font=dict(
                    size=11,
                    color=[neutral, neutral, neutral, pnl_fcolors, ret_fcolors, cum_fcolors, ann_fcolors],
                ),
                height=24,
                line_color=[year_col_line, [LIGHT_BORDER]*n, [LIGHT_BORDER]*n,
                            [LIGHT_BORDER]*n, [LIGHT_BORDER]*n, [LIGHT_BORDER]*n, [LIGHT_BORDER]*n],
                line_width=1,
            ),
        ),
        row=1, col=2,
    )

    fig.update_layout(
        template='none',
        width=1800,
        height=max(500, min(1100, n * 25 + 80)),
        title=dict(text='资金曲线 & 月度收益明细', x=0.02, xanchor='left'),
        yaxis=dict(title='资金（元）', tickformat=',.0f'),
        margin=dict(t=60, b=40, l=20, r=20),
        showlegend=False,
    )
    return fig


# ══════════════════════════════════════════════════════════
# 4. HTML 报表生成
# ══════════════════════════════════════════════════════════

def make_html(nav_df, metrics, year_ret, weekly_records, trade_df, buy_plan, sell_plan, end_date):
    # 图1: 净值曲线 + 回撤 + 指标表格
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    fig1.add_trace(go.Scatter(
        x=nav_df['date'], y=nav_df['equity_curve'],
        name='策略净值', line=dict(color='#2196F3', width=2)
    ))
    fig1.add_trace(go.Scatter(
        x=nav_df['date'], y=nav_df['drawdown'],
        name='回撤(右轴)', opacity=0.25,
        marker_color='#F44336', line=dict(width=0),
        fill='tozeroy', yaxis='y2'
    ))
    table_trace = go.Table(
        header=dict(values=['指标', '数值'],
                    fill_color='#34495e', font=dict(color='white', size=12), align='left'),
        cells=dict(values=[list(metrics.keys()), list(metrics.values())],
                   fill_color=[['#f8f9fa'] * len(metrics)],
                   align='left', font=dict(size=12)),
        domain=dict(x=[0.75, 1.0], y=[0.0, 0.85])
    )
    fig1.add_trace(table_trace)
    fig1.update_layout(
        template='none', width=1500, height=600,
        title=dict(text=f'BBI周度轮动策略  回测区间：{START_DATE} ~ {end_date}',
                   x=0.02, xanchor='left'),
        hovermode='x unified',
        xaxis=dict(domain=[0.0, 0.72]),
        yaxis=dict(title='净值'),
        yaxis2=dict(title='回撤', overlaying='y', side='right'),
        margin=dict(t=60, b=40),
        legend=dict(x=0.01, y=0.99)
    )

    # 图2: 年度收益柱状图
    year_labels = [str(d.year) for d in year_ret.index]
    year_vals = [round(v * 100, 2) for v in year_ret.values]
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=year_labels, y=year_vals,
        marker_color=['#e74c3c' if v >= 0 else '#2ecc71' for v in year_vals],
        text=[f'{v:.1f}%' for v in year_vals], textposition='outside',
    ))
    fig2.update_layout(
        template='none', width=1500, height=400,
        title=dict(text='逐年收益率', x=0.02, xanchor='left'),
        yaxis=dict(title='收益率(%)'), margin=dict(t=60, b=40)
    )

    # 图3: 下周操作计划
    plan_rows = []
    for b in buy_plan:
        plan_rows.append({'操作': '买入', '代码': b['ts_code'], '名称': b['name'],
                          '参考价': b['ref_price'], '计划股数': b['plan_shares'],
                          '计划金额': b['plan_amount'], '5日涨幅': b['5日涨幅'], '备注': b['备注']})
    for code in sell_plan:
        plan_rows.append({'操作': '卖出', '代码': code, '名称': '',
                          '参考价': '-', '计划股数': '-', '计划金额': '-', '5日涨幅': '-', '备注': '清仓'})
    plan_df = pd.DataFrame(plan_rows) if plan_rows else pd.DataFrame(
        columns=['操作', '代码', '名称', '参考价', '计划股数', '计划金额', '5日涨幅', '备注'])
    fig3 = go.Figure(data=[go.Table(
        header=dict(values=list(plan_df.columns),
                    fill_color='#2c3e50', font=dict(color='white', size=12), align='center'),
        cells=dict(values=[plan_df[c] for c in plan_df.columns],
                   fill_color=[['#fff3cd' if o == '买入' else '#f8d7da' for o in plan_df['操作']]],
                   align='center', font=dict(size=12))
    )])
    fig3.update_layout(
        width=1500, height=300,
        title=dict(text=f'下周操作计划（基于 {end_date} 数据）', x=0.02, xanchor='left'),
        margin=dict(t=50, b=10)
    )

    # 图4: 最近10周持仓周报
    week_rows = []
    for w in weekly_records[-10:]:
        for pos in w['positions']:
            week_rows.append({'换仓日': w['date'], '代码': pos['ts_code'], '名称': pos['name'],
                              '买入价': pos['cost'], '当前价': pos['price'],
                              '股数': pos['shares'], '市值': pos['market_value'],
                              '浮盈%': f"{pos['float_pnl_pct']:.2f}%"})
        week_rows.append({'换仓日': w['date'], '代码': '现金', '名称': '',
                          '买入价': '', '当前价': '', '股数': '', '市值': w['cash'], '浮盈%': ''})
    wr_df = pd.DataFrame(week_rows)
    fig4 = go.Figure(data=[go.Table(
        header=dict(values=list(wr_df.columns),
                    fill_color='#34495e', font=dict(color='white', size=11), align='center'),
        cells=dict(values=[wr_df[c] for c in wr_df.columns],
                   fill_color=[['#f0f8ff' if r['代码'] != '现金' else '#f5f5f5'
                                 for _, r in wr_df.iterrows()]],
                   align='center', font=dict(size=11))
    )])
    fig4.update_layout(
        width=1500, height=500,
        title=dict(text='最近10周持仓周报', x=0.02, xanchor='left'),
        margin=dict(t=50, b=10)
    )

    # 图5: 历史交易明细
    tr_df = trade_df.copy()
    tr_df['pnl'] = tr_df['pnl'].fillna('-')
    tr_df['pnl_pct'] = tr_df['pnl_pct'].apply(
        lambda x: f'{x:.2f}%' if pd.notna(x) and x != '-' else '-')
    fig5 = go.Figure(data=[go.Table(
        header=dict(
            values=['日期', '代码', '名称', '操作', '价格', '股数', '金额', '手续费', '盈亏(元)', '盈亏%'],
            fill_color='#34495e', font=dict(color='white', size=11), align='center'),
        cells=dict(
            values=[tr_df['date'], tr_df['ts_code'], tr_df['name'],
                    tr_df['action'], tr_df['price'], tr_df['shares'],
                    tr_df['amount'], tr_df['comm'], tr_df['pnl'], tr_df['pnl_pct']],
            fill_color=[['#fff3cd' if a == '买入' else '#d4edda' for a in tr_df['action']]],
            align='center', font=dict(size=11))
    )])
    fig5.update_layout(
        width=1500, height=min(600, max(300, len(tr_df) * 22 + 60)),
        title=dict(text=f'历史交易明细（共{len(tr_df)}笔）', x=0.02, xanchor='left'),
        margin=dict(t=50, b=10)
    )

    # 合并为单页滚动 HTML
    fig_equity = make_equity_figure(nav_df)

    section_labels = ['净值曲线', '资金曲线 & 月度收益', '年度收益', '下周操作计划', '持仓周报（最近10周）', '历史交易明细']
    sections_html = ''
    for i, (fig, label) in enumerate(zip([fig1, fig_equity, fig2, fig3, fig4, fig5], section_labels), 1):
        div = pio.to_html(fig, full_html=False, include_plotlyjs=(i == 1))
        sections_html += (
            f'<div class="section">'
            f'<div class="section-title">{label}</div>'
            f'{div}'
            f'</div>\n'
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>BBI轮动策略报表</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 0; background: #f0f2f5; }}
  .header {{ background: #2c3e50; color: white; padding: 16px 24px; }}
  .header h2 {{ margin: 0; font-size: 1.4em; }}
  .header p {{ margin: 4px 0 0; font-size: 0.9em; color: #bdc3c7; }}
  .section {{ background: white; margin: 16px; border-radius: 8px; padding: 16px; overflow-x: auto; }}
  .section-title {{ font-size: 1.05em; font-weight: bold; color: #2c3e50; margin-bottom: 8px;
                    padding-bottom: 6px; border-bottom: 2px solid #f39c12; }}
</style>
</head>
<body>
<div class="header">
  <h2>BBI周度轮动策略报表（近期5日涨幅选股）</h2>
  <p>回测区间：{START_DATE} ~ {end_date} &nbsp;|&nbsp; 初始资金：{INIT_CASH:,.0f}元 &nbsp;|&nbsp; 持仓：Top{TOP_N}只 &nbsp;|&nbsp; 排除688科创板</p>
</div>
{sections_html}
</body>
</html>"""

    out_path = OUTPUT_DIR / 'report.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Report saved: {out_path}')
    return out_path


# ══════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    nav_df, weekly_records, trade_df, last_holdings = load_results()
    metrics, year_ret, end_date = calc_metrics(nav_df)
    buy_plan, sell_plan = get_next_week_plan(last_holdings)
    out_path = make_html(nav_df, metrics, year_ret, weekly_records, trade_df,
                         buy_plan, sell_plan, end_date)
    print(f'\nDone! Opening: {out_path}')

    import subprocess, time, webbrowser
    port = 8084
    # kill 占用该端口的旧进程，确保新 http.server 服务正确的 cwd
    subprocess.run(
        f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr :{port}\') do taskkill /F /PID %a',
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    subprocess.Popen(
        ['python', '-m', 'http.server', str(port)],
        cwd=str(OUTPUT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    webbrowser.open(f'http://localhost:{port}/report.html')


if __name__ == '__main__':
    main()
