# v4_plan 数据口径与回测完整性修复 - 设计文档

## 背景

`scripts/bbi/backtrader/v4_plan` 当前存在几个会影响回测可信度的问题：

1. `20_run_backtest.py` 读取了 `v4_plan_1/output/stock_list.csv`，破坏了版本隔离。
2. `10_prepare_data.py` 用数据库最新 20 日流动性筛选全历史，存在未来数据。
3. 涨跌停成交判断使用当日 `open_qfq` 与 `close_qfq` 关系，包含日内未来信息。
4. 停牌或缺行情时，持仓估值回退到成本价，净值会失真。
5. 前复权价格同时用于信号、成交、股数、手续费，交易账本口径不严谨。
6. README 与实际代码策略不一致，报表没有明确显示回测数据口径。

用户明确要求保留“当前未退市、当前名称非 ST”作为 v4_plan 的股票池前置条件。该条件是主动选择的研究口径，不按严格 point-in-time 股票池处理；设计中必须显式暴露，避免误读为完全无幸存者偏差回测。

## 目标

本轮目标不是优化策略收益，而是先把 v4_plan 的数据契约、时点口径和版本边界修正到可审计状态：

- `v4_plan` 只读写自己的 `output`，不得依赖 `v4_plan_1`。
- 保留当前幸存者过滤，但显式配置、显式记录。
- 流动性过滤改为每日动态计算，不用未来日期筛历史。
- 涨跌停、停牌约束使用 Tushare 历史表。
- 信号价格和交易账本价格分离。
- 完整回测的账本必须处理复权事件，避免未复权价格账本在除权日失真。
- 报表显示数据口径和交易约束统计。

## 非目标

- 本轮不重新设计策略核心信号。
- 本轮不优化 ATR/硬止损/MACD/筹码退出逻辑。
- 本轮不调整数据库同步脚本。
- 本轮不操作 git。

## 头脑风暴

### 股票池

有两种口径：

1. 严格历史口径：每个交易日根据当日可知的上市、退市、ST、流动性生成股票池。
2. 用户指定研究口径：先用当前 `001_stock_basic` 排除当前退市、当前名称含 ST/退、北交所、科创板，再在这个集合内做历史回测。

本轮采用第二种，原因是用户明确表示“当前未退市、当前非 ST 名称我还是要这个条件”。实现上不能把这个条件散落在 SQL 和回测里，应集中配置：

```python
USE_CURRENT_SURVIVOR_FILTER = True
USE_HISTORICAL_ST_FILTER = True
EXCLUDE_CODE_PREFIXES = ("8", "688")
```

这样报告和 `data_quality.json` 可以明确写出：本次回测启用了当前幸存者过滤。

`USE_HISTORICAL_ST_FILTER = True` 不否定当前幸存者过滤。含义是：先用当前股票基础池排除当前退市/当前 ST，再在历史交易日上排除当日处于 ST 风险警示状态的股票。这样更贴近当日交易约束。

### 流动性

当前代码的问题是：

```sql
ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
WHERE rn <= 20
```

这会用最新 20 日过滤整个历史。正确方向是每只股票按时间序列计算：

- `amount_ma20 = amount.rolling(20).mean()`
- `circ_mv_ma20 = circ_mv.rolling(20).mean()`
- `is_liquid = amount_ma20 >= FILTER_MIN_AMOUNT and circ_mv_ma20 >= FILTER_MIN_CIRC_MV`

信号日 T 收盘后扫描，T+1 开盘买入，因此 T 日的收盘成交额、市值可以用于 T+1 决策。若以后需要更保守，可以加 `LIQUIDITY_SHIFT = 1`。

### 涨跌停

不能用当天收盘判断开盘是否可成交。应使用 `029_stk_limit`：

- 买入执行日：若 `open >= up_limit`，视为涨停买不到。
- 卖出执行日：若 `open <= down_limit`，视为跌停卖不出，保持 pending sell。
- 若 `up_limit/down_limit` 缺失，保守方案是允许成交但记录 `missing_limit_rows`；更严格方案是禁止成交。本轮建议先允许成交并统计缺失。

### 停牌和缺行情

使用 `030_suspend_d`：

- 停牌日不可买入、不可卖出、不可加仓。
- 缺行情也不可交易。
- 持仓估值使用 `last_close`，不能用成本价。

### 价格口径

信号使用前复权价格：

- `close_qfq`
- `bbi_qfq` 或本地计算的 `bbi_qfq`
- `macd` 可继续基于 `close_qfq`

交易账本使用未复权价格：

- `open`
- `close`
- `up_limit/down_limit`
- 股数、现金、佣金、PnL

ATR/硬止损如果暂时保留，也必须和交易账本同单位，ATR 应基于未复权 `high/low/close`。

### 复权事件

严格账本需要用 `adj_factor` 处理除权除息引发的持仓股数/成本变化。否则未复权成交价账本会在除权日出现虚假损益。

本轮不应把完整复权账本完全后置。实现分两层：

1. P1 必须完成最小可用的 `adj_factor` 持仓调整，保证多年完整回测的 NAV/PnL 不因除权日断裂。
2. P2 再完善现金分红、送转细节审计和逐笔复权调整日志。

最小调整规则：

- 每个持仓记录保存上一交易日 `adj_factor`。
- 当持仓股票当日 `adj_factor` 与上一持仓日不一致时，按比例调整持仓股数和成本价。
- 调整前后持仓市值应尽量连续。
- 若 `adj_factor` 缺失，记录到 `run_stats.json`，并在报表中提示。

### 前端/报表

报表不是只画净值，应展示回测口径：

- 是否启用当前幸存者过滤。
- 是否启用历史 ST 过滤。
- 股票池数量、导出股票数量。
- 流动性过滤后每日候选数量。
- 涨停买入跳过次数。
- 跌停卖出延期次数。
- 停牌跳过次数。
- 缺失 limit 行数、缺失行情估值次数。
- 关键数据表最大日期：行情因子、涨跌停、停牌、筹码。

## 数据来源

本地文档位于 `docs/tushare/tushare.pro/document`。

| 用途 | 表 | 字段 |
|---|---|---|
| 当前股票基础池 | `001_stock_basic` | `ts_code`, `name`, `list_date`, `delist_date`, `market`, `exchange`, `list_status` |
| 行情与因子 | `063_stk_factor_pro` | `open`, `high`, `low`, `close`, `open_qfq`, `high_qfq`, `low_qfq`, `close_qfq`, `amount`, `circ_mv`, `adj_factor` |
| 涨跌停 | `029_stk_limit` | `trade_date`, `ts_code`, `up_limit`, `down_limit`, `pre_close` |
| 停牌 | `030_suspend_d` | `trade_date`, `ts_code`, `suspend_type`, `suspend_timing` |
| 筹码退出 | `061_cyq_perf` | `winner_rate`，继续 `shift(1)` |
| 历史 ST | `004_stock_st` | `trade_date`, `ts_code`, `type_name` |

## 数据契约

### `10_prepare_data.py` 输出

`output/stock_list.csv`

- 当前研究股票池。
- 必须来自本目录脚本，不得借用 `v4_plan_1`。
- 字段建议：`ts_code`, `name`, `list_date`, `delist_date`, `market`, `exchange`, `list_status`。

`output/stock_data/{ts_code}.parquet`

必须包含：

- 日期：`trade_date`
- 交易账本价：`open`, `high`, `low`, `close`
- 信号价：`open_qfq`, `high_qfq`, `low_qfq`, `close_qfq`, `bbi_qfq`
- 成交辅助：`vol`, `amount`, `circ_mv`, `adj_factor`
- 动态过滤：`amount_ma20`, `circ_mv_ma20`, `list_days`, `is_liquid`, `is_eligible`
- 交易约束：`up_limit`, `down_limit`, `is_suspended`
- 可选：`is_st`, `winner_rate`

`output/universe_daily.parquet`

- 每日每股过滤状态快照。
- 用于 debug、报表统计和后续 review。

`output/data_quality.json`

- 记录本次数据准备的配置和统计。
- 记录关键表最大日期，至少包括：
  - `max_factor_date`
  - `max_limit_date`
  - `max_suspend_date`
  - `max_cyq_date`
  - `max_stock_st_date`

### `20_run_backtest.py` 输入

只允许读取：

- `v4_plan/output/stock_list.csv`
- `v4_plan/output/stock_data/*.parquet`
- `v4_plan/output/universe_daily.parquet`，如果需要整体统计

禁止读取：

- `v4_plan_1/*`
- `tmp/*`
- 其他版本输出

### `20_run_backtest.py` 输出

`nav_series.csv`、`trade_records.csv`、`last_holdings.json` 保持兼容。

新增：

`run_stats.json`

```json
{
  "skipped_limit_up_buys": 0,
  "limit_down_sell_delays": 0,
  "suspended_trade_skips": 0,
  "missing_quote_valuations": 0,
  "missing_limit_rows": 0,
  "missing_adj_factor_rows": 0,
  "adj_factor_adjustments": 0,
  "eligible_scan_rows": 0,
  "candidate_rows": 0
}
```

## 回测时点

每日循环：

1. 在 T 日开盘执行 T-1 日产生的 pending sell/add/buy。
2. 使用未复权 `open` 成交。
3. 若 T 日停牌或无行情，不成交。
4. 若买入且 `open >= up_limit`，跳过买入。
5. 若卖出且 `open <= down_limit`，保持 pending sell。
6. 若持仓股票 `adj_factor` 变化，先调整持仓股数和成本，再计算当日持仓市值。
7. T 日收盘后更新持仓估值、信号、出场、加仓、新候选。
8. T 日收盘生成的 pending action 在 T+1 开盘执行。

## 风险与取舍

- 保留当前幸存者过滤会带来幸存者偏差，这是用户指定口径，必须在报告中显示。
- 如果 `029_stk_limit` 缺失，按允许成交处理会偏乐观；按禁止成交处理会偏保守。本轮建议允许并统计。
- 未复权账本必须至少处理 `adj_factor` 股数/成本调整；现金分红等更细节审计可放 P2。
- `063_stk_factor_pro` 已含技术指标，但本轮继续本地计算 BBI/MACD，减少对第三方指标公式变化的依赖。

## 验收标准

1. `rg "v4_plan_1" scripts/bbi/backtrader/v4_plan` 无结果。
2. `10_prepare_data.py` 能生成 `stock_list.csv`、逐股 parquet、`universe_daily.parquet`、`data_quality.json`。
3. `20_run_backtest.py` 只读本目录输出。
4. 交易记录中的成交价使用未复权 `open`。
5. 涨跌停判断不再引用当天 `close`。
6. 停牌/无行情日不成交，估值使用上一可用收盘。
7. 报表展示本次回测数据口径和约束统计。
8. `data_quality.json` 展示关键表最大日期。
9. `adj_factor` 变化时有持仓调整统计，完整区间 NAV 不应在除权日因账本口径断裂。
10. 小区间回测能跑通，完整区间可重复运行。
