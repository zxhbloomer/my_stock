# v4_plan 数据口径与回测完整性修复 - 执行计划

## 当前状态

在计划文档补齐前，已经产生了两处未完成实现改动：

- `scripts/bbi/backtrader/v4_plan/config.py`
- `scripts/bbi/backtrader/v4_plan/10_prepare_data.py`

后续实现必须先 review 这两处改动，确认和设计一致，再继续修改其他文件。不得操作 git。

## 执行原则

- 先设计，后实现，再 review。
- `v4_plan` 与 `v4_plan_1` 完全隔离。
- 保留用户指定的当前幸存者过滤，并在输出和报表中显式声明。
- 修数据时点优先于调策略参数。
- 每个阶段先跑最小验证，再跑完整流程。

## Phase 0 - 设计确认

输入：

- `docs/superpowers/specs/2026-05-09-v4_plan-data-integrity-design.md`

确认点：

- 是否接受 `USE_CURRENT_SURVIVOR_FILTER = True` 作为显式研究口径。
- 是否接受 `USE_HISTORICAL_ST_FILTER = True`，即当前基础池内仍按历史交易日排除当日 ST。
- 是否接受流动性使用 T 日滚动 20 日均值，用于 T+1 开盘交易。
- 是否接受缺失涨跌停数据时允许成交但统计缺失。
- 是否接受 P1 完成最小 `adj_factor` 持仓调整，P2 再完善现金分红和调整日志。

完成标准：

- 用户确认或提出修改意见。

## Phase 1 - 数据准备脚本

文件：

- `scripts/bbi/backtrader/v4_plan/config.py`
- `scripts/bbi/backtrader/v4_plan/10_prepare_data.py`

任务：

1. Review 当前已改动内容，保证没有语法错误和字段名错误。
2. `config.py` 增加数据口径配置：
   - `LIQUIDITY_LOOKBACK`
   - `USE_CURRENT_SURVIVOR_FILTER`
   - `USE_HISTORICAL_ST_FILTER`
   - `EXCLUDE_CODE_PREFIXES`
   - `UNIVERSE_DATA_PATH`
   - `DATA_QUALITY_PATH`
   - `RUN_STATS_PATH`
3. `10_prepare_data.py` 生成：
   - `output/stock_list.csv`
   - `output/stock_data/*.parquet`
   - `output/universe_daily.parquet`
   - `output/data_quality.json`
4. 逐股 parquet 增加：
   - 未复权 OHLC：`open`, `high`, `low`, `close`
   - 前复权信号价：`open_qfq`, `high_qfq`, `low_qfq`, `close_qfq`
   - 动态流动性：`amount_ma20`, `circ_mv_ma20`, `is_liquid`
   - 上市天数：`list_days`, `is_listed_long_enough`
   - 交易约束：`up_limit`, `down_limit`, `is_suspended`
   - 股票资格：`is_eligible`
5. 不再使用“数据库最新 20 日”筛选全历史。
6. 增加命令行参数，便于开发验证：
   - `--start YYYY-MM-DD`
   - `--end YYYY-MM-DD`
   - `--codes 000001.SZ,600000.SH`
7. `data_quality.json` 记录关键表最大日期：
   - `063_stk_factor_pro`
   - `029_stk_limit`
   - `030_suspend_d`
   - `061_cyq_perf`
   - `004_stock_st`

验证：

```powershell
cd scripts/bbi/backtrader/v4_plan
python -X utf8 -m py_compile config.py 10_prepare_data.py
```

小范围运行方式：

```powershell
python -X utf8 10_prepare_data.py --start 2018-01-01 --end 2018-03-31 --codes 000001.SZ,600000.SH
```

Review 清单：

- 是否还存在 `ROW_NUMBER() ... ORDER BY trade_date DESC` 的流动性筛选。
- 是否把 `winner_rate` 做了 `shift(1)`。
- 是否所有输出都在 `v4_plan/output`。
- 是否 `stock_list.csv` 包含口径审计字段。
- 是否 `data_quality.json` 包含关键表最大日期。

## Phase 2 - 回测脚本

文件：

- `scripts/bbi/backtrader/v4_plan/20_run_backtest.py`

任务：

1. 移除 `v4_plan_1/output/stock_list.csv` 依赖。
2. `load_stocks()` 只读本目录：
   - `OUTPUT_DIR / "stock_list.csv"`
   - `STOCK_DATA_DIR.glob("*.parquet")`
3. `build_panel()` 增加字段：
   - `open`, `close`
   - `up_limit`, `down_limit`
   - `is_suspended`, `is_eligible`
   - `amount_ma20`, `circ_mv_ma20`
4. 成交函数改为未复权 `open`。
5. 信号函数继续使用 `close_qfq` 和 `bbi_qfq`。
6. 买入扫描只允许 `is_eligible == True` 的股票。
7. 涨跌停判断：
   - 买入：`open >= up_limit` 跳过。
   - 加仓：`open >= up_limit` 跳过。
   - 卖出：`open <= down_limit` 延期。
8. 停牌判断：
   - `is_suspended == True` 不成交。
9. 持仓估值：
   - 持仓记录维护 `last_close`。
   - 当天有行情则用当天未复权 `close` 更新。
   - 当天缺行情则使用 `last_close`。
10. 最小 `adj_factor` 持仓调整：
   - 持仓记录维护 `last_adj_factor`。
   - 当日 `adj_factor` 变化时调整 `shares` 和 `cost_price`。
   - 调整前后持仓市值应尽量连续。
   - 缺失 `adj_factor` 记录到 `run_stats.json`。
11. 输出 `run_stats.json`。

验证：

```powershell
cd scripts/bbi/backtrader/v4_plan
python -X utf8 -m py_compile 20_run_backtest.py
python -X utf8 20_run_backtest.py
```

Review 清单：

- `rg "v4_plan_1" scripts/bbi/backtrader/v4_plan` 必须无结果。
- `is_limit_up/is_limit_down` 不得使用当天 `close_qfq` 判断成交。
- 成交金额、手续费、PnL 使用未复权价格。
- 信号排序 `ret5` 不得包含当天以后数据。
- 无行情估值不得回退到 `cost_price`。
- 除权日附近 NAV 不应因未复权账本产生明显断裂。

## Phase 3 - 报表脚本

文件：

- `scripts/bbi/backtrader/v4_plan/30_generate_report.py`

任务：

1. 读取并展示 `data_quality.json`。
2. 读取并展示 `run_stats.json`。
3. 当前持仓展示中区分：
   - 成本价：未复权账本成本
   - 最新价：未复权最新收盘
   - 信号价可选展示 `close_qfq`
4. 顶部 header 增加口径：
   - 当前幸存者过滤：是/否
   - 历史 ST 过滤：是/否
   - 流动性窗口：20 日
5. 增加交易约束统计 section：
   - 涨停买入跳过
   - 跌停卖出延期
   - 停牌跳过
   - 缺失行情估值
   - 缺失涨跌停行
   - 复权调整次数
   - 缺失复权因子行
6. 增加数据新鲜度 section：
   - 因子数据最大日期
   - 涨跌停数据最大日期
   - 停牌数据最大日期
   - 筹码数据最大日期
   - ST 数据最大日期

验证：

```powershell
cd scripts/bbi/backtrader/v4_plan
python -X utf8 -m py_compile 30_generate_report.py
python -X utf8 30_generate_report.py
```

Review 清单：

- 报表不应暗示这是严格无幸存者偏差回测。
- 表格字段单位要明确。
- 当前持仓浮盈使用未复权价格口径。
- 报表必须显示关键表最大日期，避免新旧数据混用不可见。

## Phase 4 - 文档同步

文件：

- `scripts/bbi/backtrader/v4_plan/README.md`

任务：

1. 修正 README 与代码不一致的问题。
2. 明确 v4_plan 当前实际策略是每日 BBI 金叉择时组合，不是每周 Top5 轮动，除非代码另行改回周度策略。
3. 增加数据口径说明：
   - 当前幸存者过滤
   - 动态流动性
   - 涨跌停/停牌约束
   - 信号价与成交价分离
4. 增加输出文件说明：
   - `universe_daily.parquet`
   - `data_quality.json`
   - `run_stats.json`
5. 明确说明 P1 已做最小 `adj_factor` 持仓调整，现金分红细节审计留给后续。

验证：

```powershell
rg -n "每周一|Top 5|没有 ATR|weekly_records" scripts/bbi/backtrader/v4_plan/README.md
```

Review 清单：

- README 不得描述不存在的输出。
- README 不得把研究口径写成严格无未来函数口径。

## Phase 5 - 端到端验证

前提：

- 用户确认数据已经更新完成。

命令：

```powershell
cd scripts/bbi/backtrader/v4_plan
python -X utf8 10_prepare_data.py
python -X utf8 20_run_backtest.py
python -X utf8 30_generate_report.py
```

检查：

1. `output/stock_list.csv` 存在且行数合理。
2. `output/universe_daily.parquet` 存在且包含 `is_eligible`。
3. `output/data_quality.json` 记录口径。
4. `output/run_stats.json` 记录约束统计。
5. `trade_records.csv` 中买入成交日没有 `open >= up_limit`。
6. `trade_records.csv` 中卖出成交日没有 `open <= down_limit`。
7. `run_stats.json` 中有 `adj_factor_adjustments` 和 `missing_adj_factor_rows`。
8. 报表能打开，口径显示清楚。
9. 报表显示关键表最大日期。

## Phase 6 - 代码 Review

重点 review 项：

1. 版本隔离
   - 不读 `v4_plan_1`。
   - 不读 `tmp`。
2. 时点正确性
   - 流动性滚动窗口不使用未来。
   - T 日信号 T+1 执行。
   - 涨跌停成交不使用当天收盘判断。
3. 价格单位
   - 信号用 qfq。
   - 交易账本用未复权。
   - ATR/硬止损如保留，单位必须和账本一致。
4. 估值
   - 停牌/缺行情用 `last_close`。
   - 不用 `cost_price` 代替市值。
5. 复权账本
   - 持仓期间 `adj_factor` 变化会调整股数和成本。
   - 缺失 `adj_factor` 有统计。
   - 除权日前后市值连续性合理。
6. 输出
   - 所有新增 JSON/CSV/parquet 可重复生成。
   - 报表展示口径，不隐藏幸存者过滤。

## 后续任务

P2 单独处理：

- 完善现金分红、送转等复权调整审计日志。
- 把止损模块开关化，便于单独评估。
