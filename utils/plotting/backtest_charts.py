import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

COLOR_STRATEGY = "#2196F3"
COLOR_BENCHMARK = "#9E9E9E"
COLOR_DRAWDOWN = "salmon"
COLOR_RETURN = "#34a853"
COLOR_BUY = "red"
COLOR_SELL = "green"
MONTH_LABELS = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]

_LAYOUT_DEFAULTS = dict(
    template="plotly",
    margin=dict(l=0, r=0, b=0, t=40),
    hovermode="x unified",
)


def plot_cumulative_returns(returns_df: pd.DataFrame, title: str = "累计收益曲线") -> go.Figure:
    """绘制累计收益曲线，支持多列策略对比。"""
    cum_df = (1 + returns_df).cumprod() - 1
    fig = px.line(cum_df, title=title)
    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        xaxis_title=None,
        yaxis_title="累计收益",
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5),
    )
    # 年份边界红色虚线
    years = cum_df.index.year.unique()
    for yr in years[1:]:
        boundary = cum_df.index[cum_df.index.year == yr][0]
        fig.add_vline(x=boundary, line_dash="dash", line_color="red", line_width=1)
    return fig


def plot_drawdown_analysis(returns: pd.Series, title: str = "回撤分析") -> go.Figure:
    """绘制回撤分析图，左轴回撤，右轴累计收益。"""
    cum_ret = (1 + returns).cumprod() - 1
    drawdown = cum_ret - cum_ret.cummax()

    fig = go.Figure()
    # 左轴：回撤（salmon填充）
    fig.add_trace(go.Scatter(
        x=drawdown.index, y=drawdown * 100,
        name="回撤(%)", fill="tozeroy",
        line=dict(color=COLOR_DRAWDOWN),
        yaxis="y1",
    ))
    # 右轴：累计收益（绿线）
    fig.add_trace(go.Scatter(
        x=cum_ret.index, y=cum_ret,
        name="累计收益", line=dict(color=COLOR_RETURN),
        yaxis="y2",
    ))
    # 分位数水平虚线
    for q in [10, 30, 50]:
        y_val = float(np.percentile(drawdown * 100, q))
        fig.add_shape(
            type="line",
            x0=0, x1=1, xref="paper",
            y0=y_val, y1=y_val, yref="y",
            line=dict(dash="dot", color="rgba(128,128,128,0.5)", width=1),
        )
        fig.add_annotation(
            x=0, xref="paper", y=y_val, yref="y",
            text=f"{q}%分位: {y_val:.2f}%",
            showarrow=False, xanchor="left",
            font=dict(size=10, color="gray"),
        )
    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title=title,
        yaxis=dict(title="净值回撤(%)"),
        yaxis2=dict(title="累计收益", overlaying="y", side="right"),
    )
    return fig


def plot_monthly_heatmap(returns: pd.Series, title: str = "月度收益热力图") -> go.Figure:
    """绘制月度收益热力图。"""
    df = returns.copy()
    df = df.to_frame(name="ret")
    df["year"] = df.index.year
    df["month"] = df.index.month
    monthly = df.groupby(["year", "month"])["ret"].sum() * 100
    pivot = monthly.unstack(level="month")
    # 确保12列都存在
    for m in range(1, 13):
        if m not in pivot.columns:
            pivot[m] = np.nan
    pivot = pivot[list(range(1, 13))]

    z = pivot.values
    y_labels = [str(yr) for yr in pivot.index]
    text = [[f"{v:.2f}%" if not np.isnan(v) else "" for v in row] for row in z]

    fig = go.Figure(go.Heatmap(
        z=z, x=MONTH_LABELS, y=y_labels,
        colorscale="RdYlGn",
        text=text, texttemplate="%{text}",
        hovertemplate="%{y}年%{x}<br>收益: %{z:.2f}%<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title=title,
        xaxis_title="月份",
        yaxis_title="年份",
    )
    return fig


def plot_return_distribution(returns: pd.Series, title: str = "收益分布") -> go.Figure:
    """绘制收益率分布直方图，标注均值和±1σ。"""
    pct = (returns * 100).dropna()
    if len(pct) == 0:
        return go.Figure()
    fig = px.histogram(pct, nbins=50, title=title)
    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        xaxis_title="收益率(%)",
        yaxis_title="频数",
    )
    mean_val = pct.mean()
    std_val = pct.std()
    fig.add_vline(x=mean_val, line_dash="dash", line_color="blue",
                  annotation_text="均值", annotation_position="top right")
    fig.add_vline(x=mean_val + std_val, line_dash="dash", line_color="orange",
                  annotation_text="+1σ", annotation_position="top right")
    fig.add_vline(x=mean_val - std_val, line_dash="dash", line_color="orange",
                  annotation_text="-1σ", annotation_position="top left")
    return fig


def plot_candlestick_bbi_signals(price_df: pd.DataFrame, trades_df: pd.DataFrame,
                                 title: str = "K线 · BBI · 买卖信号") -> go.Figure:
    """K线图 + BBI线 + 买卖信号标注 + 成交量副图（共享X轴）。

    price_df 需包含列: open, high, low, close, volume, bbi
    trades_df 需包含列: date, action, price
    """
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.03,
    )

    # ── 主图：K线 ──────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=price_df.index,
        open=price_df["open"],
        high=price_df["high"],
        low=price_df["low"],
        close=price_df["close"],
        name="K线",
        increasing_line_color="#F44336",
        decreasing_line_color="#4CAF50",
        increasing_fillcolor="#F44336",
        decreasing_fillcolor="#4CAF50",
    ), row=1, col=1)

    # ── 主图：收盘价折线 ───────────────────────────────
    fig.add_trace(go.Scatter(
        x=price_df.index, y=price_df["close"],
        name="收盘价", line=dict(color="#2196F3", width=1),
        opacity=0.6,
    ), row=1, col=1)

    # ── 主图：BBI线 ────────────────────────────────────
    if "bbi" in price_df.columns:
        fig.add_trace(go.Scatter(
            x=price_df.index, y=price_df["bbi"],
            name="BBI", line=dict(color="#FF9800", dash="dash", width=1.5),
        ), row=1, col=1)

    # ── 主图：买卖信号 ─────────────────────────────────
    if trades_df is not None and not trades_df.empty:
        # 统一 date 列为 Timestamp，避免与 DatetimeIndex 的 x 轴类型冲突
        trades_df = trades_df.copy()
        trades_df["date"] = pd.to_datetime(trades_df["date"])
        buys  = trades_df[trades_df["action"] == "买入"]
        sells = trades_df[trades_df["action"] == "卖出"]
        if len(buys) > 0:
            # 买入标记在最低价下方
            buy_y = []
            for d in buys["date"]:
                row_data = price_df[price_df.index == pd.Timestamp(d)]
                y = float(row_data["low"].iloc[0]) * 0.985 if len(row_data) > 0 else float(buys.loc[buys["date"]==d, "price"].iloc[0])
                buy_y.append(y)
            fig.add_trace(go.Scatter(
                x=buys["date"], y=buy_y,
                mode="markers+text",
                name="买入",
                marker=dict(symbol="triangle-up", color="#F44336", size=12),
                text=buys["price"].apply(lambda p: f"买{p:.2f}"),
                textposition="bottom center",
                textfont=dict(size=9, color="#F44336"),
            ), row=1, col=1)
        if len(sells) > 0:
            # 卖出标记在最高价上方
            sell_y = []
            for d in sells["date"]:
                row_data = price_df[price_df.index == pd.Timestamp(d)]
                y = float(row_data["high"].iloc[0]) * 1.015 if len(row_data) > 0 else float(sells.loc[sells["date"]==d, "price"].iloc[0])
                sell_y.append(y)
            fig.add_trace(go.Scatter(
                x=sells["date"], y=sell_y,
                mode="markers+text",
                name="卖出",
                marker=dict(symbol="triangle-down", color="#4CAF50", size=12),
                text=sells["price"].apply(lambda p: f"卖{p:.2f}"),
                textposition="top center",
                textfont=dict(size=9, color="#4CAF50"),
            ), row=1, col=1)

    # ── 副图：成交量（涨红跌绿）─────────────────────────
    if "volume" in price_df.columns:
        colors = [
            "#F44336" if c >= o else "#4CAF50"
            for c, o in zip(price_df["close"], price_df["open"])
        ]
        fig.add_trace(go.Bar(
            x=price_df.index, y=price_df["volume"],
            name="成交量", marker_color=colors, showlegend=False,
        ), row=2, col=1)

    fig.update_layout(
        template="plotly_white",
        margin=dict(l=0, r=0, b=0, t=40),
        hovermode="x unified",
        title=title,
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
        xaxis_type="date",
        xaxis2_type="date",
        yaxis_title="价格",
        yaxis2_title="成交量",
        legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5),
        height=650,
        dragmode="zoom",
    )
    # 关闭 rangeslider；隐藏非交易日空白（周末+A股节假日）；x轴中文日期格式
    fig.update_xaxes(
        rangeslider_visible=False,
        rangebreaks=[
            dict(bounds=["sat", "mon"]),           # 隐藏周末
            dict(values=[                           # 隐藏A股主要节假日
                "2025-01-01","2025-01-28","2025-01-29","2025-01-30",
                "2025-01-31","2025-02-03","2025-02-04",
                "2025-04-04","2025-04-05","2025-04-06",
                "2025-05-01","2025-05-02","2025-05-05",
                "2025-05-31","2025-06-01","2025-06-02",
                "2025-10-01","2025-10-02","2025-10-03","2025-10-04",
                "2025-10-05","2025-10-06","2025-10-07","2025-10-08",
                "2026-01-01",
                "2026-01-26","2026-01-27","2026-01-28","2026-01-29",
                "2026-01-30","2026-02-02","2026-02-03","2026-02-04",
            ]),
        ],
        tickformat="%Y年%-m月",   # x轴刻度：2025年9月
    )
    return fig


def plot_price_bbi_signals(price_df: pd.DataFrame, trades_df: pd.DataFrame,
                           title: str = "价格与BBI信号") -> go.Figure:
    fig = go.Figure()
    # 收盘价（蓝线）
    fig.add_trace(go.Scatter(
        x=price_df.index, y=price_df["close"],
        name="收盘价", line=dict(color=COLOR_STRATEGY),
    ))
    # BBI线（橙色虚线）
    if 'bbi' in price_df.columns:
        fig.add_trace(go.Scatter(
            x=price_df.index, y=price_df["bbi"],
            name="BBI", line=dict(color="#FF9800", dash="dash"),
        ))
    # 买卖信号
    if trades_df is not None and not trades_df.empty:
        buys = trades_df[trades_df["action"] == "买入"]
        sells = trades_df[trades_df["action"] == "卖出"]
        if len(buys) > 0:
            fig.add_trace(go.Scatter(
                x=buys["date"], y=buys["price"],
                mode="markers", name="买入",
                marker=dict(symbol="triangle-up", color=COLOR_BUY, size=10),
            ))
        if len(sells) > 0:
            fig.add_trace(go.Scatter(
                x=sells["date"], y=sells["price"],
                mode="markers", name="卖出",
                marker=dict(symbol="triangle-down", color=COLOR_SELL, size=10),
            ))
    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title=title,
        xaxis_title="日期",
        yaxis_title="价格",
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5),
    )
    return fig
