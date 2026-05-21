# tmp_v5 Bear Defensive Quality Design

## 目标

在不修改正式 `v4`、`v5`、`v6` 代码与输出的前提下，继续沿着 `v6` 已合入的熊市右侧试探买入思路演化：

- 不放松 `v6` 的熊市门禁。
- 只在 `bear_probe` 已经允许开仓时，再用更防御的候选筛选/排序。
- 优先验证是否能改善收益，至少不能明显恶化最大回撤。

## 背景结论

本地已有实验已经给出三个重要事实：

1. 直接放松熊市门禁，容易提升 2018 强股捕获，但组合收益和回撤通常更差。
2. `moneyflow` / `cyq_perf` 作为新增信号，在现有 `v6` 上没有带来稳定增益。
3. 上涨趋势、预熊确认、纯门禁修补，大多没有优于当前 `v6`。

因此，本轮不再做“是否放开熊市”的实验，而做“熊市里买什么”的实验。

## 外部依据

通过 `tavily-search` 复核后的共识：

- 熊市/弱市中的经典防御因子是 `low volatility` 与 `quality`。
- `quality` 更稳的定义偏向盈利能力、低杠杆、现金流质量，而不是泛泛的“好公司”。
- `dividend` 在中国 A 股可作为成熟、现金流稳定公司的代理，但更适合作为辅助项。
- `relative strength` 在防御框架里应作为确认条件，而不是主导信号。

## 数据范围

复用正式 `v6` 已落地数据：

- `scripts/bbi/backtrader/v6/output/panel.parquet`
- `scripts/bbi/backtrader/v6/output/market_index.parquet`

新增只读数据库表：

- `tushare_v2."027_daily_basic"`
- `tushare_v2."042_fina_indicator"`

## PIT 规则

### 日频字段

`daily_basic` 按 `ts_code + trade_date` 直接对齐到 `panel.trade_date`。

因为策略使用 `signal_date=T` 的收盘后信息，在 `T+1` 开盘交易，所以 `T` 日快照可用于 `T+1`。

### 财务字段

`fina_indicator` 必须按 `ann_date <= trade_date` 做 `merge_asof(direction="backward")`。

本轮采用保守口径：

- 只按 `ann_date` 生效，不按 `end_date` 回填。
- 不做前向填补之外的任何插值。
- 如果 `ann_date = T`，则该数据可以参与 `signal_date = T`，并在 `T+1` 开盘交易。

## 因子设计

只服务于 `bear_probe` 候选，不改普通 `v6` 买入路径。

### 防御基础字段

- 低波：`volatility_63`
- 相对强度：`ret_63 - market_ret_60`
- 股息代理：`dv_ttm`
- 估值代理：`pb`
- 盈利质量：`roe_dt`, `grossprofit_margin`, `ocf_to_or`
- 资产负债表防御：`debt_to_assets`

### 防御综合分

定义横截面 `bear_defensive_score`：

```text
+ 0.25 * z(roe_dt)
+ 0.20 * z(grossprofit_margin)
+ 0.15 * z(ocf_to_or)
- 0.20 * z(debt_to_assets)
- 0.15 * z(volatility_63)
+ 0.10 * z(dv_ttm)
- 0.05 * z(pb)
+ 0.10 * z(relative_strength_63)
```

其中：

- `relative_strength_63 = ret_63 - market_ret_60`
- 缺失值不做激进填补，只在横截面上用中位数补到评分流程里。

## 实验变体

以当前正式 `v6` 为基线，比较以下变体：

1. `baseline_v6`
   - 当前 `v6` 行为，不改熊市试探候选。

2. `defensive_filter`
   - 熊市试探时要求：
     - `relative_strength_63 > 0`
     - `volatility_63 <= 截面中位数`
     - `roe_dt >= 截面中位数`
     - `debt_to_assets <= 截面中位数`

3. `defensive_score`
   - 熊市试探时不加硬过滤，只对候选加入 `bear_defensive_score` 排序增强。

4. `defensive_filter_score`
   - 熊市试探时先走 `defensive_filter`，再按 `bear_defensive_score` 重排。

## 成功标准

优先级按顺序判断：

1. 全周期总收益高于当前 `v6`
2. 年化收益高于当前 `v6`
3. 最大回撤不比当前 `v6` 恶化超过 3 个百分点
4. 2018 年度收益至少不明显差于当前 `v6`

若没有变体同时满足 1 和 3，则不建议合并。

## 产物

- 实验脚本：`scripts/bbi/backtrader/tmp/tmp_v5_bear_defensive_quality_experiment.py`
- 测试脚本：`scripts/bbi/backtrader/tmp/test_tmp_v5_bear_defensive_quality.py`
- 进度记录：`scripts/bbi/backtrader/tmp/tmp_v5_bear_defensive_quality_README.md`
- 报表目录：`scripts/bbi/backtrader/tmp/tmp_v5_bear_defensive_quality_output/`

