# v4_plan 周度开盘调仓重写设计

日期：2026-05-09

## 背景

`scripts/bbi/backtrader/v4_plan` 当前实际运行的是每日 BBI 金叉入场、止损、ATR 跟踪止损、死叉退出、筹码退出和加仓混合策略。该逻辑与本轮目标不一致，且已有输出显示结果很差，仓位和加仓会造成严重集中。

本轮不保留旧策略主循环，重写 `20_run_backtest.py` 为周度开盘调仓组合策略。`v4_plan` 与 `v4_plan_1` 继续保持隔离，不读取相邻版本输出。

## 目标策略

策略目标是验证一个简单、可解释、无日内未来信息的周度组合：

1. 每周第一个实际交易日开盘买入。
2. 每周最后一个实际交易日开盘卖出。
3. 节假日按真实交易日处理。
4. 不考虑止损，不使用 ATR 跟踪止损，不使用 BBI 死叉退出，不使用 MACD 死叉退出，不使用筹码退出。
5. 不加仓。
6. 买入信号严格参考 `scripts/bbi/backtrader/v3` 的入场逻辑。
7. 涨停开盘买不了，跌停开盘卖不出。
8. 延迟卖出会占用资金和仓位，延迟卖出成功当天不买入。

## 数据口径

沿用 `10_prepare_data.py` 输出：

- `output/stock_data/{ts_code}.parquet`
- `output/universe_daily.parquet`
- `output/stock_list.csv`
- `output/data_quality.json`

信号使用前复权字段：

- `close_qfq`
- `bbi_qfq`
- `macd`
- `macd_signal`

`macd` 与 `macd_signal` 必须与 v3 的 Backtrader MACD 参数一致：

- `MACD_FAST = 12`
- `MACD_SLOW = 26`
- `MACD_SIGNAL = 9`

如果 `10_prepare_data.py` 生成或补算 MACD，必须使用同一套参数，并在验证阶段抽样对比 v3 入场判断，确认同一只股票同一信号日的 `_entry_signal()` 结果一致。

交易账本使用未复权字段：

- `open`
- `close`
- `up_limit`
- `down_limit`
- `adj_factor`

交易约束使用动态字段：

- `is_eligible`
- `is_suspended`
- `is_st`
- `is_liquid`

日线回测不使用当日 `high`、`low` 或盘中是否打开涨跌停来判断成交。

## 买入信号

买入信号严格参考 v3 的 `_entry_signal()`。

对信号日 `T`：

1. 至少有最近 4 个交易点。
2. `T-1` 日 `close_qfq < bbi_qfq`。
3. `T` 日 `close_qfq > bbi_qfq`。
4. `T` 日 `bbi_qfq > T-3` 日 `bbi_qfq`。
5. `T` 日 MACD 满足 `macd > macd_signal` 或 `macd > 0`。
6. `T` 日股票满足动态股票池资格。

实际买入日在 `T+1` 开盘执行。若因为延迟卖出导致买入推迟，则使用实际买入日前一个交易日作为新的信号日重新计算名单。

## 排序规则

排序不能使用全周期绩效汇总。每个信号日只能使用该日及以前可见数据。

候选股票先全部满足 v3 买入信号，再排序。

第一版排序采用 rolling 候选观察绩效优先，`ret5` 兜底：

1. 对每个候选股票，统计信号日及以前已经完成的候选观察交易。
2. 候选观察交易包括真实买入股票，也包括满足候选条件但因仓位限制未被选中的股票。
3. 候选观察交易按本策略同样的买入/卖出执行约束计算结果：
   - 如果观察买入日停牌、无有效开盘价或开盘涨停，则该观察交易记为不可建仓，不进入 rolling 绩效样本。
   - 如果观察买入成功，则按该周最后实际交易日开盘卖出。
   - 如果观察卖出日跌停、停牌或无有效开盘价，则按 pending sell 规则延迟到第一个可卖出开盘日。
   - 只有观察卖出完成后，该观察交易才能参与后续信号日的 rolling 绩效统计。
4. 如果该股票已完成观察交易数 `trade_count >= 5`，进入绩效排序组。
5. 绩效排序组按以下顺序排序：
   - `avg_return_pct` 降序
   - `calmar` 降序
   - `win_rate` 降序
   - `ret5` 降序
   - `ts_code` 升序作为稳定兜底
6. `trade_count < 5` 的候选股票进入样本不足组，排在绩效排序组之后。
7. 样本不足组按以下顺序排序：
   - `ret5` 降序
   - `ts_code` 升序

`ret5` 定义为信号日前最近约 5 个交易日的前复权收盘涨幅：

```text
ret5 = 最近可见 close_qfq / 约 5 个交易日前 close_qfq - 1
```

rolling 绩效来自本次组合回测已经完成的候选观察交易，而不是 v3 全历史输出，也不是只来自真实买入股票。这样可以避免排序样本只偏向早期被选中的股票。

rolling 指标定义：

- `trade_count`：信号日及以前已完成的候选观察交易数。
- `win_rate`：已完成候选观察交易中 `return_pct > 0` 的比例。
- `avg_return_pct`：已完成候选观察交易的算术平均收益率。
- `calmar`：用该股票已完成候选观察交易按完成时间构造权益曲线，初始权益为 1，每笔收益按 `equity *= (1 + return_pct / 100)` 复利；`max_drawdown = min(equity / cumulative_peak - 1)`；`annual_return = equity_end ** (365 / span_days) - 1`，其中 `span_days` 是第一笔观察买入日至最后一笔观察卖出日的自然日跨度，最小按 1 天处理；`calmar = annual_return / max(abs(max_drawdown), 0.01)`，并裁剪到 `[-10, 10]`，避免零回撤或极小样本导致排序失真。

## 交易日历和调仓状态机

使用 `panel["trade_date"].unique()` 构建真实交易日历，并按自然周分组。

每个自然周：

- 第一个实际交易日是计划买入日。
- 最后一个实际交易日是计划卖出日。
- 如果某个自然周只有一个实际交易日，该日只允许处理已有持仓卖出或 pending sell，不新开仓。

每日开盘处理顺序：

1. 应用复权因子调整持仓股数和成本。
2. 优先尝试卖出所有 `pending_sell` 持仓。
3. 如果当天有延迟卖出成功，记录 `skip_buy_today=True`，当天不买入。
4. 如果当天是计划卖出日，尝试卖出普通持仓。
5. 如果当天允许买入，且还有可用仓位和现金，用前一交易日收盘数据重新选股并开盘买入。
6. 日终按收盘价估值并记录 NAV。

买入允许条件必须实现为一个明确布尔表达式：

```text
can_buy =
    (is_week_first_trade_day or delayed_buy_pending)
    and not is_week_last_trade_day
    and not skip_buy_today
    and available_slots > 0
    and cash >= MIN_COMMISSION
```

其中：

- `delayed_buy_pending` 表示前期因为卖出延迟导致本轮周度买入尚未完成。
- `skip_buy_today` 表示当天发生了 pending sell 成功卖出，释放资金不参与当天买入。
- `available_slots = MAX_SLOTS - 当前持仓数`，当前持仓数包含 pending sell 遗留仓位。

如果仍有旧仓位未卖出：

- 旧仓位继续占用资金。
- 旧仓位继续占用仓位名额。
- 新买入数量上限为 `MAX_SLOTS - 当前持仓数`。

## 成交规则

买入：

- 停牌、缺少开盘价、开盘价无效：不成交。
- `open >= up_limit`：视为涨停买不了，不成交。
- 其他情况按 `open` 成交。

卖出：

- 停牌、缺少开盘价、开盘价无效：不成交，转为或保持 `pending_sell`。
- `open <= down_limit`：视为跌停卖不出，转为或保持 `pending_sell`。
- 其他情况按 `open` 成交。

集合竞价挂涨停价买入不单独建模。日线回测中，非涨停开盘时按开盘价成交；涨停开盘时保守视为买不到。

## 资金和仓位

第一版不做加仓，不做同日二次买入。

仓位规则：

- 最大持仓数使用 `MAX_SLOTS`。
- 当前持仓数包含 `pending_sell` 遗留仓位。
- 可买数量为 `MAX_SLOTS - 当前持仓数`。
- 每只目标金额按组合目标仓位计算，避免把剩余现金集中压到单只股票。
- 推荐目标金额为 `total_assets / MAX_SLOTS`，实际买入金额不超过可用现金。
- 买入股数按 100 股一手向下取整。
- 佣金按 `COMMISSION_BUY`、`COMMISSION_SELL`、`MIN_COMMISSION` 计算。

卖出成功当天释放的资金不参与当天买入。最早下一交易日使用最新可见数据重新选股。

## 输出文件

保留：

- `output/nav_series.csv`
- `output/trade_records.csv`
- `output/last_holdings.json`
- `output/run_stats.json`

新增：

- `output/candidate_rank_records.csv`
- `output/trade_events.csv`

`candidate_rank_records.csv` 字段：

- `signal_date`
- `buy_date`
- `ts_code`
- `name`
- `rank`
- `selected`
- `ret5`
- `trade_count`
- `win_rate`
- `avg_return_pct`
- `calmar`
- `score_group`
- `skip_reason`
- `observed`
- `observation_buy_price`
- `observation_sell_date`
- `observation_sell_price`
- `observation_return_pct`
- `observation_status`

说明：

- `candidate_rank_records.csv` 记录每个买入日的全部候选排序，不只记录真实买入股票。
- `selected=True` 表示进入真实组合买入计划。
- `observed=True` 表示该候选在观察交易中可建仓并最终形成可统计结果。
- `observation_status` 包括 `completed`、`unbuyable_limit_up`、`unbuyable_suspended`、`open`。

`trade_records.csv` 增加或保留字段：

- `date`
- `ts_code`
- `name`
- `action`
- `price`
- `shares`
- `amount`
- `comm`
- `pnl`
- `pnl_pct`
- `reason`

`trade_records.csv` 只记录真实成交。`reason` 示例：

- `weekly_buy`
- `weekly_exit`
- `pending_sell_exit`

`trade_events.csv` 记录未成交事件和延迟事件，字段：

- `date`
- `ts_code`
- `name`
- `event`
- `reason`
- `price`
- `up_limit`
- `down_limit`
- `pending_days`

`event` 示例：

- `limit_up_skip`
- `limit_down_delay`
- `suspended_delay`

`run_stats.json` 需要包含：

- `candidate_rows`
- `selected_rows`
- `skipped_limit_up_buys`
- `limit_down_sell_delays`
- `suspended_trade_skips`
- `pending_sell_successes`
- `buy_days`
- `sell_days`
- `max_pending_sell_days`
- `avg_pending_sell_days`
- `missing_quote_valuations`
- `missing_limit_rows`
- `missing_adj_factor_rows`
- `adj_factor_adjustments`

## 报表

`30_generate_report.py` 同步周度策略口径：

- 展示周度开盘调仓说明。
- 不展示加仓、止损、ATR、死叉、筹码退出作为策略核心。
- 展示候选排序统计。
- 展示涨停买入失败次数。
- 展示跌停/停牌卖出延迟次数、最大延迟天数、平均延迟天数。
- 当前持仓展示是否 `pending_sell`。
- 交易记录展示 `reason`。

## 验证

不操作 git。

验证步骤：

1. `python -X utf8 -m py_compile` 检查 `config.py`、`20_run_backtest.py`、`30_generate_report.py`。
2. 静态搜索确认主策略不再包含旧逻辑关键字：
   - `HARD_STOP_LOSS`
   - `PYRAMID`
   - `trail_stop`
   - `chip_exit`
   - `death_cross`
   - `pending_add`
3. 静态搜索确认没有 `v4_plan_1` 依赖。
4. 运行 `20_run_backtest.py`。
5. 运行 `30_generate_report.py`。
6. 检查 `trade_records.csv`：
   - 买入发生在允许买入日。
   - 周度卖出发生在每周最后实际交易日或 pending sell 后续日。
   - 无加仓记录。
7. 检查 `candidate_rank_records.csv`：
   - 每次买入日前都有候选排序记录。
   - 排序指标只使用 `signal_date` 及以前的数据。
   - rolling 绩效来自已完成候选观察交易，不读取未来候选结果。
8. 抽样验证 MACD 和 v3 `_entry_signal()` 一致。
9. 抽样验证 `adj_factor` 调整方向：
   - 选择至少一只有除权除息的股票。
   - 检查除权日前后持仓市值不因股数/成本调整方向错误产生异常跳变。
   - 检查卖出 PnL 与未复权成交价格、调整后股数和成本一致。

## 不在本轮做

- 不引入实盘委托队列模拟。
- 不使用日内高低价判断涨跌停是否打开。
- 不读取 v3 全历史绩效作为排序指标。
- 不保留旧每日策略作为可选模式。
- 不操作 git。
