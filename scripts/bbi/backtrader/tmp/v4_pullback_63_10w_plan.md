# v4 63日回撤与10周线实验计划

## 目标

在不修改 `scripts/bbi/backtrader/v4` 主策略的前提下，使用 `v4/output/panel.parquet` 已有数据，比较 63 日高点回撤与 10 周均线回踩条件，判断是否比当前 `pullback_120 <= -9%` 更适合寻找强势股买点。

## 原则

- 只在 `scripts/bbi/backtrader/tmp` 中实验。
- 不重新准备数据，不修改 `v4/10_prepare_data.py`。
- 只读 `v4/output/panel.parquet`、`v4/output/market_index.parquet`、`v4/output/nav_series.csv`。
- 回测仍复用 `v4/20_run_backtest.py` 的成交、止损、仓位和风控逻辑。
- 交易日开盘只使用上一完整交易日 `signal_date` 的数据，不使用未来数据。

## 实验字段

- `high_qfq_63`：每只股票近 63 个交易日最高前复权收盘价。
- `pullback_63`：`close_qfq / high_qfq_63 - 1`。
- `ma10w`：每只股票按周末收盘价计算的 10 周均线，再映射回日线。
- `dist_10w`：`close_qfq / ma10w - 1`。
- `ma10w_slope`：本周 `ma10w` 相对上一周 `ma10w` 的变化率。

## 参数组

| 组 | 63日回撤 | 10周线条件 | 目的 |
|---|---:|---|---|
| A | `<= -5%` | 不加 | 只验证 120 日改 63 日 |
| B | `<= -7%` | 不加 | 中性回撤阈值 |
| C | `<= -9%` | 不加 | 和原 `-9%` 对照，只改周期 |
| D | `<= -5%` | `abs(dist_10w) <= 3%` 且 `ma10w_slope > 0` | 贴近上升10周线的轻回踩 |
| E | `<= -7%` | `abs(dist_10w) <= 5%` 且 `ma10w_slope > 0` | 贴近上升10周线的中性回踩 |
| F | `<= -9%` | `abs(dist_10w) <= 8%` 且 `ma10w_slope > 0` | 贴近上升10周线的深回踩 |

每组再分两个市场口径：

- `base`：沿用 v4 当前短期大跌过滤。
- `ma120`：在 `base` 基础上，要求上证指数 `signal_date` 收盘价高于 120 日均线才允许新开仓。

## 输出

- `scripts/bbi/backtrader/tmp/v4_pullback_63_10w_output/results.csv`
- `scripts/bbi/backtrader/tmp/v4_pullback_63_10w_output/summary.md`

## 验收

- 每组输出 2018 年收益、最大回撤、Calmar、交易数、买入次数、卖出次数。
- 同时输出 2018 到当前可用数据结束日的全区间结果，防止只对 2018 过拟合。
- 结论优先看：2018 是否亏损显著减少、牛市是否仍能开仓、交易次数是否过少。
