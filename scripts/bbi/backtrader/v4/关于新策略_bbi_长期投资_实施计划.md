# 关于新策略：BBI 长期投资实施计划

> 最新 tmp 实验已将首笔买入回撤口径调整为分层规则：普通股票 `63 日回撤 <= -5%`，强趋势股票 `63 日回撤 <= -3%`。本文早期的 `120 日回撤 9%` 仅作为历史设计记录。

## 目标

在 v4 中实现一套长期持有策略：沿用现有 v4 强势排名，等待候选股从阶段高点回撤后买入，按 `8 万 + 6 万 + 4 万 + 2 万` 分批建仓，最多持有 5 只，总投入最多 50 万，单票最多 20 万，并加入 -5% 止损、跌停硬止损、盈利持仓放量大阴线次日卖出。

## 文件职责

- `config.py`：新增长期策略参数。
- `10_prepare_data.py`：补充回测需要的字段和衍生特征。
- `20_run_backtest.py`：实现长期策略主流程。
- `30_generate_report.py`：补充交易原因中文展示。
- `关于新策略_bbi_长期投资_算法.md`：保持设计说明同步。

## 实施步骤

### 1. 配置参数

- 新增长期策略参数：
  - `LONG_MAX_HOLDINGS = 5`
  - `LONG_MAX_TOTAL_EXPOSURE = 500_000.0`
  - `LONG_POSITION_STEPS = (80_000.0, 60_000.0, 40_000.0, 20_000.0)`
  - `LONG_PULLBACK_LOOKBACK = 120`
  - `LONG_PULLBACK_THRESHOLD = -0.05`
  - `LONG_STRONG_TREND_PULLBACK_THRESHOLD = -0.03`
  - `LONG_STOP_LOSS_PCT = -0.05`
  - `LONG_ADD_PROFIT_THRESHOLDS = (0.05, 0.10, 0.15)`
  - `LONG_BEARISH_DROP_THRESHOLD = -0.07`
  - `LONG_BEARISH_AMOUNT_MULTIPLIER = 1.5`
  - `LONG_BEARISH_CLOSE_LOW_POSITION = 0.25`

### 2. 数据准备

- `063_stk_factor_pro` 查询补充：
  - `high`
  - `low`
  - `pre_close`
- `add_strength_features()` 补充：
  - `high_qfq_120 = rolling_max(close_qfq, 120)`
  - `pullback_63 = close_qfq / high_qfq_63 - 1`
- 输出 `panel.parquet` 中保留这些字段。

### 3. 回测主流程

- 保留现有 `score_candidates()`，强势排名沿用 v4。
- 交易频率改为每日：
  - `T` 日收盘计算信号。
  - `T+1` 日开盘执行。
- 买入逻辑：
  - 选候选排名前 `KEEP_TOP_N`。
  - 普通股票必须满足 `pullback_63 <= -0.05`。
  - 强趋势股票必须满足 `pullback_63 <= -0.03`。
  - 未持仓、未刚触发风险卖出。
  - 持仓数小于 5。
  - 总投入小于 50 万。
  - 第一次买入金额 8 万。
- 加仓逻辑：
  - 只对已有持仓。
  - 亏损不加仓。
  - 第 2/3/4 笔分别要求整仓累计浮盈达到 5%/10%/15%。
  - 每次加仓金额分别为 6 万、4 万、2 万。
  - 单票总投入不超过 20 万，总投入不超过 50 万。
- 卖出逻辑：
  - 持仓亏损达到 -5%，次日开盘清仓。
  - 持仓期间出现跌停，次日开盘清仓，卖不出顺延。
  - 盈利持仓出现放量大阴线，次日开盘清仓，卖不出顺延。
  - 不再因为排名跌出就卖出。
  - 盈利持仓跌破 BBI 不卖出。

### 4. 报表

- 交易原因中文化：
  - `long_initial_buy`
  - `long_add_buy`
  - `long_stop_loss`
  - `long_limit_down_exit`
  - `long_bearish_volume_exit`
- 当前持仓显示：
  - 建仓阶段。
  - 已投入金额。

### 5. 验证

- 语法检查：
  - `python -m py_compile scripts/bbi/backtrader/v4/10_prepare_data.py scripts/bbi/backtrader/v4/20_run_backtest.py scripts/bbi/backtrader/v4/30_generate_report.py`
- 不主动运行完整回测，除非明确要求。
- 检查是否存在未来函数：
  - 所有买卖信号使用 `i - 1` 的 `signal_panel`。
  - 所有成交使用 `i` 的开盘价。
