"""
BBI周度轮动策略 — HTML报表生成器（方法C：近期涨幅）
风格参考邢不行选股框架：Plotly净值曲线 + 指标表格 + 年度分析 + 交易明细 + 下周计划
"""
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import warnings
warnings.filterwarnings('ignore')

# ── 路径 ──────────────────────────────────────────────────
BASE_DIR   = Path(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v3')
STOCK_DIR  = BASE_DIR / 'output' / 'stock_data'
TRADES_CSV = BASE_DIR / 'output' / 'trades_detail.csv'
STOCK_LIST = BASE_DIR / 'output' / 'stock_list.csv'
OUT_DIR    = Path(r'D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp')

INIT_CASH   = 500_000.0
TOP_N       = 5
COMM_BUY    = 0.0005
COMM_SELL   = 0.0015
MIN_COMM    = 5.0
START_DATE  = '2018-01-01'
END_DATE    = '2026-04-24'
RISK_FREE   = 0.02


# ══════════════════════════════════════════════════════════
# 1. 回测引擎（方法C，记录每周持仓和交易明细）
# ══════════════════════════════════════════════════════════

def load_stocks():
    stock_list = pd.read_csv(STOCK_LIST)
    valid = set(stock_list[~stock_list['ts_code'].str.startswith('688')]['ts_code'])
    name_map = dict(zip(stock_list['ts_code'], stock_list['name']))
    data = {}
    for f in STOCK_DIR.glob('*.parquet'):
        code = f.stem
        if code not in valid:
            continue
        df = pd.read_parquet(f)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df = df.sort_values('trade_date').reset_index(drop=True)
        df = df[(df['trade_date'] >= START_DATE) & (df['trade_date'] <= END_DATE)]
        if len(df) < 60:
            continue
        data[code] = df
    print(f'Loaded {len(data)} stocks')
    return data, name_map


def build_panel(data):
    frames = []
    for code, df in data.items():
        tmp = df[['trade_date', 'close_qfq', 'bbi_qfq']].copy()
        tmp['ts_code'] = code
        frames.append(tmp)
    return pd.concat(frames, ignore_index=True).sort_values(['trade_date', 'ts_code']).reset_index(drop=True)


def get_weekly_mondays(panel):
    dates = pd.DataFrame({'date': sorted(panel['trade_date'].unique())})
    dates['year'] = dates['date'].dt.isocalendar().year.astype(int)
    dates['week'] = dates['date'].dt.isocalendar().week.astype(int)
    return dates.groupby(['year', 'week'])['date'].min().sort_values().tolist()


def calc_comm(amount, is_buy):
    return max(amount * (COMM_BUY if is_buy else COMM_SELL), MIN_COMM)


def run_method_c(data, panel):
    """方法C回测，返回 nav_df, weekly_records, trade_records"""
    print('Running Method C backtest...')
    mondays = get_weekly_mondays(panel)
    all_dates = sorted(panel['trade_date'].unique())
    panel_by_date = {d: panel[panel['trade_date'] == d].set_index('ts_code') for d in all_dates}

    cash = INIT_CASH
    holdings = {}   # code -> {shares, cost_price, buy_date, name}
    nav_series = []
    weekly_records = []   # 每周持仓快照
    trade_records = []    # 每笔买卖记录

    monday_set = set(mondays)
    prev_date = None

    # 预加载name_map
    stock_list = pd.read_csv(STOCK_LIST)
    name_map = dict(zip(stock_list['ts_code'], stock_list['name']))

    for date in all_dates:
        day_panel = panel_by_date[date]

        if date in monday_set:
            # 选股：BBI上方 + 5日涨幅最强
            above = day_panel[day_panel['close_qfq'] > day_panel['bbi_qfq']].copy()

            # 计算5日涨幅
            if prev_date is not None:
                ret5_list = []
                for code in above.index:
                    if code in data:
                        df_c = data[code]
                        hist = df_c[df_c['trade_date'] <= date].tail(6)
                        if len(hist) >= 2:
                            r = hist['close_qfq'].iloc[-1] / hist['close_qfq'].iloc[0] - 1
                        else:
                            r = 0.0
                        ret5_list.append((code, r))
                if ret5_list:
                    ret5_df = pd.DataFrame(ret5_list, columns=['ts_code', 'ret5']).set_index('ts_code')
                    above = above.join(ret5_df, how='left').fillna(0)
                    new_picks = above.nlargest(TOP_N, 'ret5').index.tolist()
                else:
                    new_picks = []
            else:
                new_picks = above.index.tolist()[:TOP_N]

            new_set = set(new_picks)
            cur_set = set(holdings.keys())

            # 卖出
            for code in cur_set - new_set:
                if code not in day_panel.index:
                    continue
                price = float(day_panel.loc[code, 'close_qfq'])
                shares = holdings[code]['shares']
                proceeds = price * shares
                comm = calc_comm(proceeds, False)
                pnl = proceeds - comm - holdings[code]['cost_price'] * shares
                pnl_pct = pnl / (holdings[code]['cost_price'] * shares) * 100
                cash += proceeds - comm
                trade_records.append({
                    'date': date, 'ts_code': code,
                    'name': name_map.get(code, code),
                    'action': '卖出',
                    'price': round(price, 3),
                    'shares': shares,
                    'amount': round(proceeds, 0),
                    'comm': round(comm, 1),
                    'pnl': round(pnl, 0),
                    'pnl_pct': round(pnl_pct, 2),
                    'hold_weeks': None,
                })
                del holdings[code]

            # 买入
            alloc = min(cash / max(len(new_set - cur_set), 1), INIT_CASH / TOP_N * 1.2)
            for code in new_set - cur_set:
                if code not in day_panel.index:
                    continue
                price = float(day_panel.loc[code, 'close_qfq'])
                if price <= 0:
                    continue
                shares = int(alloc / price / 100) * 100
                if shares <= 0:
                    continue
                cost = price * shares
                comm = calc_comm(cost, True)
                if cash < cost + comm:
                    shares = int((cash - MIN_COMM) / price / 100) * 100
                    if shares <= 0:
                        continue
                    cost = price * shares
                    comm = calc_comm(cost, True)
                cash -= cost + comm
                holdings[code] = {
                    'shares': shares, 'cost_price': price,
                    'buy_date': date, 'name': name_map.get(code, code)
                }
                trade_records.append({
                    'date': date, 'ts_code': code,
                    'name': name_map.get(code, code),
                    'action': '买入',
                    'price': round(price, 3),
                    'shares': shares,
                    'amount': round(cost, 0),
                    'comm': round(comm, 1),
                    'pnl': None, 'pnl_pct': None,
                    'hold_weeks': None,
                })

            # 记录本周持仓快照
            week_val = cash
            week_pos = []
            for code, pos in holdings.items():
                p = float(day_panel.loc[code, 'close_qfq']) if code in day_panel.index else pos['cost_price']
                mv = p * pos['shares']
                week_val += mv
                week_pos.append({
                    'date': date,
                    'ts_code': code,
                    'name': pos['name'],
                    'cost': round(pos['cost_price'], 3),
                    'price': round(p, 3),
                    'shares': pos['shares'],
                    'market_value': round(mv, 0),
                    'float_pnl_pct': round((p / pos['cost_price'] - 1) * 100, 2),
                })
            weekly_records.append({
                'date': date,
                'positions': week_pos,
                'cash': round(cash, 0),
                'total_nav': round(week_val, 0),
            })

        # 日净值
        pv = cash
        for code, pos in holdings.items():
            p = float(day_panel.loc[code, 'close_qfq']) if code in day_panel.index else pos['cost_price']
            pv += p * pos['shares']
        nav_series.append({'date': date, 'nav': pv})
        prev_date = date

    nav_df = pd.DataFrame(nav_series)
    nav_df['date'] = pd.to_datetime(nav_df['date'])
    nav_df['equity_curve'] = nav_df['nav'] / INIT_CASH
    nav_df['pct_chg'] = nav_df['equity_curve'].pct_change().fillna(0)
    nav_df['max2here'] = nav_df['equity_curve'].expanding().max()
    nav_df['drawdown'] = nav_df['equity_curve'] / nav_df['max2here'] - 1

    print(f'Backtest done. Final NAV: {nav_df["nav"].iloc[-1]:,.0f}')
    return nav_df, weekly_records, trade_records


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

    # 年度收益
    nav_df2 = nav_df.set_index('date')
    year_ret = nav_df2['pct_chg'].resample('YE').apply(lambda x: (1 + x).prod() - 1)

    return {
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
    }, year_ret


# ══════════════════════════════════════════════════════════
# 3. 下周操作计划
# ══════════════════════════════════════════════════════════

def get_next_week_plan(data, panel, current_holdings_codes):
    """基于最新数据生成下周操作计划"""
    latest_date = panel['trade_date'].max()
    day_panel = panel[panel['trade_date'] == latest_date].set_index('ts_code')
    above = day_panel[day_panel['close_qfq'] > day_panel['bbi_qfq']].copy()

    ret5_list = []
    for code in above.index:
        if code in data:
            hist = data[code].tail(6)
            if len(hist) >= 2:
                r = hist['close_qfq'].iloc[-1] / hist['close_qfq'].iloc[0] - 1
            else:
                r = 0.0
            ret5_list.append((code, r))

    if not ret5_list:
        return [], []

    ret5_df = pd.DataFrame(ret5_list, columns=['ts_code', 'ret5']).set_index('ts_code')
    above = above.join(ret5_df, how='left').fillna(0)
    new_picks = above.nlargest(TOP_N, 'ret5').index.tolist()

    stock_list = pd.read_csv(STOCK_LIST)
    name_map = dict(zip(stock_list['ts_code'], stock_list['name']))

    buy_plan = []
    for code in new_picks:
        price = float(day_panel.loc[code, 'close_qfq'])
        alloc = INIT_CASH / TOP_N
        shares = int(alloc / price / 100) * 100
        buy_plan.append({
            'ts_code': code,
            'name': name_map.get(code, code),
            'ref_price': round(price, 3),
            'plan_shares': shares,
            'plan_amount': round(price * shares, 0),
            '5日涨幅': f"{float(above.loc[code, 'ret5'])*100:.2f}%",
        })

    sell_plan = [c for c in current_holdings_codes if c not in set(new_picks)]
    return buy_plan, sell_plan


# ══════════════════════════════════════════════════════════
# 4. HTML报表生成
# ══════════════════════════════════════════════════════════

def make_html(nav_df, metrics, year_ret, weekly_records, trade_records, buy_plan, sell_plan, last_holdings):
    # ── 图1: 净值曲线 + 回撤 + 指标表格 ──────────────────
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

    # 右侧指标表格
    metric_keys = list(metrics.keys())
    metric_vals = list(metrics.values())
    table_trace = go.Table(
        header=dict(values=['指标', '数值'],
                    fill_color='#34495e', font=dict(color='white', size=12),
                    align='left'),
        cells=dict(values=[metric_keys, metric_vals],
                   fill_color=[['#f8f9fa'] * len(metric_keys)],
                   align='left', font=dict(size=12)),
        domain=dict(x=[0.75, 1.0], y=[0.0, 0.85])
    )
    fig1.add_trace(table_trace)
    fig1.update_layout(
        template='none', width=1500, height=600,
        title=dict(text=f'BBI周度轮动策略（方法C：近期涨幅）  回测区间：{START_DATE} ~ {END_DATE}',
                   x=0.02, xanchor='left'),
        hovermode='x unified',
        hoverlabel=dict(bgcolor='rgba(255,255,255,0.8)'),
        xaxis=dict(domain=[0.0, 0.72]),
        yaxis=dict(title='净值'),
        yaxis2=dict(title='回撤', overlaying='y', side='right'),
        margin=dict(t=60, b=40),
        legend=dict(x=0.01, y=0.99)
    )
    fig1.update_yaxes(showspikes=True, spikemode='across', spikesnap='cursor',
                      spikedash='solid', spikethickness=1)
    fig1.update_xaxes(showspikes=True, spikemode='across+marker', spikesnap='cursor',
                      spikedash='solid', spikethickness=1)

    # ── 图2: 年度收益柱状图 ───────────────────────────────
    year_labels = [str(d.year) for d in year_ret.index]
    year_vals = [round(v * 100, 2) for v in year_ret.values]
    colors = ['#e74c3c' if v >= 0 else '#2ecc71' for v in year_vals]

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=year_labels, y=year_vals,
        marker_color=colors,
        text=[f'{v:.1f}%' for v in year_vals],
        textposition='outside',
        name='年度收益率'
    ))
    fig2.update_layout(
        template='none', width=1500, height=400,
        title=dict(text='逐年收益率', x=0.02, xanchor='left'),
        yaxis=dict(title='收益率(%)'),
        xaxis=dict(title='年份'),
        margin=dict(t=60, b=40)
    )

    # ── 图3: 交易明细表 ───────────────────────────────────
    tr_df = pd.DataFrame(trade_records)
    tr_df['date'] = tr_df['date'].astype(str).str[:10]
    tr_df['pnl'] = tr_df['pnl'].fillna('-')
    tr_df['pnl_pct'] = tr_df['pnl_pct'].apply(lambda x: f'{x:.2f}%' if pd.notna(x) and x != '-' else '-')

    fig3 = go.Figure(data=[go.Table(
        header=dict(
            values=['日期', '代码', '名称', '操作', '价格', '股数', '金额', '手续费', '盈亏(元)', '盈亏%'],
            fill_color='#34495e', font=dict(color='white', size=11),
            align='center'
        ),
        cells=dict(
            values=[
                tr_df['date'], tr_df['ts_code'], tr_df['name'],
                tr_df['action'], tr_df['price'], tr_df['shares'],
                tr_df['amount'], tr_df['comm'], tr_df['pnl'], tr_df['pnl_pct']
            ],
            fill_color=[['#fff3cd' if a == '买入' else '#d4edda'
                         for a in tr_df['action']]],
            align='center', font=dict(size=11)
        )
    )])
    fig3.update_layout(
        width=1500, height=min(600, max(300, len(tr_df) * 22 + 60)),
        title=dict(text=f'历史交易明细（共{len(tr_df)}笔）', x=0.02, xanchor='left'),
        margin=dict(t=50, b=10)
    )

    # ── 图4: 最近10周持仓周报 ─────────────────────────────
    recent_weeks = weekly_records[-10:]
    week_rows = []
    for w in recent_weeks:
        date_str = str(w['date'])[:10]
        for pos in w['positions']:
            week_rows.append({
                '换仓日': date_str,
                '代码': pos['ts_code'],
                '名称': pos['name'],
                '买入价': pos['cost'],
                '当前价': pos['price'],
                '股数': pos['shares'],
                '市值': pos['market_value'],
                '浮盈%': f"{pos['float_pnl_pct']:.2f}%",
            })
        week_rows.append({
            '换仓日': date_str, '代码': '现金', '名称': '',
            '买入价': '', '当前价': '', '股数': '',
            '市值': w['cash'], '浮盈%': '',
        })

    wr_df = pd.DataFrame(week_rows)
    fig4 = go.Figure(data=[go.Table(
        header=dict(
            values=list(wr_df.columns),
            fill_color='#34495e', font=dict(color='white', size=11),
            align='center'
        ),
        cells=dict(
            values=[wr_df[c] for c in wr_df.columns],
            fill_color=[['#f0f8ff' if r['代码'] != '现金' else '#f5f5f5'
                         for _, r in wr_df.iterrows()]],
            align='center', font=dict(size=11)
        )
    )])
    fig4.update_layout(
        width=1500, height=500,
        title=dict(text='最近10周持仓周报', x=0.02, xanchor='left'),
        margin=dict(t=50, b=10)
    )

    # ── 图5: 下周操作计划 ─────────────────────────────────
    plan_rows = []
    for b in buy_plan:
        plan_rows.append({
            '操作': '买入',
            '代码': b['ts_code'],
            '名称': b['name'],
            '参考价': b['ref_price'],
            '计划股数': b['plan_shares'],
            '计划金额': b['plan_amount'],
            '5日涨幅': b['5日涨幅'],
            '备注': '新建仓' if b['ts_code'] not in last_holdings else '继续持有',
        })
    for code in sell_plan:
        plan_rows.append({
            '操作': '卖出',
            '代码': code,
            '名称': '',
            '参考价': '-',
            '计划股数': '-',
            '计划金额': '-',
            '5日涨幅': '-',
            '备注': '清仓',
        })

    plan_df = pd.DataFrame(plan_rows) if plan_rows else pd.DataFrame(
        columns=['操作', '代码', '名称', '参考价', '计划股数', '计划金额', '5日涨幅', '备注'])

    fig5 = go.Figure(data=[go.Table(
        header=dict(
            values=list(plan_df.columns),
            fill_color='#2c3e50', font=dict(color='white', size=12),
            align='center'
        ),
        cells=dict(
            values=[plan_df[c] for c in plan_df.columns],
            fill_color=[['#fff3cd' if o == '买入' else '#f8d7da'
                         for o in plan_df['操作']]],
            align='center', font=dict(size=12)
        )
    )])
    fig5.update_layout(
        width=1500, height=300,
        title=dict(text=f'下周操作计划（基于 {END_DATE} 数据）', x=0.02, xanchor='left'),
        margin=dict(t=50, b=10)
    )

    # ── 合并为单个HTML（单页滚动，无tab）────────────────────
    section_labels = ['净值曲线', '年度收益', '下周操作计划', '持仓周报（最近10周）', '历史交易明细']
    sections_html = ''
    for i, (fig, label) in enumerate(zip([fig1, fig2, fig5, fig4, fig3], section_labels), 1):
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
  <h2>BBI周度轮动策略报表（方法C：近期5日涨幅）</h2>
  <p>回测区间：{START_DATE} ~ {END_DATE} &nbsp;|&nbsp; 初始资金：{INIT_CASH:,.0f}元 &nbsp;|&nbsp; 持仓：Top{TOP_N}只 &nbsp;|&nbsp; 排除688科创板</p>
</div>
{sections_html}
</body>
</html>"""

    out_path = OUT_DIR / 'rotation_report.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Report saved: {out_path}')
    return out_path


# ══════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════

def main():
    data, name_map = load_stocks()
    panel = build_panel(data)

    nav_df, weekly_records, trade_records = run_method_c(data, panel)

    metrics, year_ret = calc_metrics(nav_df)

    # 最后一周持仓
    last_holdings = set()
    if weekly_records:
        for pos in weekly_records[-1]['positions']:
            last_holdings.add(pos['ts_code'])

    buy_plan, sell_plan = get_next_week_plan(data, panel, last_holdings)

    out = make_html(nav_df, metrics, year_ret, weekly_records, trade_records,
                    buy_plan, sell_plan, last_holdings)
    print(f'\nDone! Open: {out}')


if __name__ == '__main__':
    main()
