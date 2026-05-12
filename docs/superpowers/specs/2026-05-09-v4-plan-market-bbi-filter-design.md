# v4_plan 上证指数 BBI 过滤设计

## 目标

在 `scripts/bbi/backtrader/v4_plan` 增加大盘环境过滤：买入日前一个已完成交易日的上证指数 `close > bbi_bfq` 时，才允许本周第一个买入窗口开新仓；否则本周空仓，不在周内补买，等下周第一个实际交易日重新判断。

## 数据来源

- 指数代码：`000001.SH`，名称：上证指数。
- 数据表：`tushare_v2."137_idx_factor_pro"`。
- 使用字段：`trade_date`, `close`, `bbi_bfq`。
- `bbi_bfq` 来自 Tushare 指数技术面因子，不在本地重算。

## 数据流

`10_prepare_data.py` 从数据库读取上证指数数据，保存为 `output/market_index.parquet`。`20_run_backtest.py` 只读取该 output 文件，不直接查询数据库。

买入日 `T` 开盘前，回测使用 `signal_date = T-1` 的指数数据判断市场状态：

- `close > bbi_bfq`：允许按现有个股 BBI 金叉逻辑选股买入。
- `close <= bbi_bfq`：本次买入窗口不买任何股票。
- 找不到 `signal_date` 指数数据或 `bbi_bfq` 缺失：按保守口径不买。

## 行为边界

- 不改变个股买入信号。
- 不改变每周最后一个实际交易日开盘卖出。
- 不改变跌停、停牌导致的延迟卖出。
- 不在周二、周三因为指数重新站上 BBI 而补买。
- 因跌停延迟卖出导致下周买入窗口被推迟的场景，仍按已有逻辑使用实际买入日前一交易日重新判断指数状态。

## 输出与报表

- `data_quality.json` 记录指数数据来源、代码、最大日期和过滤规则。
- `run_stats.json` 记录市场过滤跳过的买入日数、缺失指数信号日数。
- HTML 报表头部展示大盘过滤规则和统计。

## 验证

- 编译 `config.py`、`10_prepare_data.py`、`20_run_backtest.py`、`30_generate_report.py`。
- 用小区间运行 v4_plan 三步，检查 `market_index.parquet`、`run_stats.json`、`report.html` 是否产生并包含大盘过滤信息。
