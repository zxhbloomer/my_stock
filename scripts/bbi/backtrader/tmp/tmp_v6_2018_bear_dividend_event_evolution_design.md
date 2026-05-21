# tmp_v6 2018 独立熊市分红事件进化设计

## 目标

继续只优化独立熊市 long-only 策略，不接入 `v6` 的空仓逻辑。聚焦 2018 年，验证 `041_dividend` 的 PIT 分红事件因子能否比当前基于 `dv_ttm` 的独立熊市版本更稳，并和 `v4`、`v5`、`v6` 同表对比。

## 外部研究与专家约束

Tavily 检索到的 S&P、MSCI、CAIA 与中文研究共识是：

- 熊市里 A 股 long-only 更现实的目标是少亏和缩小回撤。
- 红利、低波、质量是防御组合的核心，但红利因子必须避免未来函数。
- 对分红事件，`ann_date` 代表市场可见性，`ex_date` 代表真正落地，二者不能混用。

策略专家评审建议：

1. 主版本优先测试 `ex_date` 严格口径。
2. `ann_date` 口径只做诊断，不直接当正式结论。
3. 同一 `ts_code + end_date` 可能多次公告，任一时点只能保留截至当时最新已知状态。

## 本地数据

- 价格、可交易、热钱风险、停牌等：`scripts/bbi/backtrader/v6/output/panel.parquet`
- 市场指数：`scripts/bbi/backtrader/v6/output/market_index.parquet`
- 分红事件：`tushare_v2."041_dividend"`
  - 主键：`ts_code`, `end_date`, `ann_date`
  - 关键字段：`cash_div_tax`, `record_date`, `ex_date`, `div_proc`
- 估值：`tushare_v2."027_daily_basic"` 的 `pb`, `pe_ttm`
- 质量：`tushare_v2."042_fina_indicator"`，按 `ann_date <= signal_date` backward merge
- 行业：`tushare_v2."001_stock_basic".industry`

## 分红事件因子定义

### V1: `event_ex_date_strict_30_monthly`

- 每个交易日 `t`：
  - 对每个 `ts_code + end_date`，只保留 `ann_date <= t` 的最新记录
  - 仅当该记录 `ex_date <= t` 且 `cash_div_tax > 0` 时，视为已实施分红
  - 对过去 12 个月内已实施现金分红求和
  - 再除以 `t` 当日价格，得到 `pit_div_yield_strict`
- 这是主版本，直接替代原 `dv_ttm`

### V2: `event_ann_date_known_30_monthly`

- 对每个交易日 `t`：
  - 对每个 `ts_code + end_date`，只保留 `ann_date <= t` 的最新记录
  - 只要 `cash_div_tax > 0` 就计入过去 12 个月滚动和，不要求 `ex_date <= t`
  - 除以 `t` 当日价格，得到 `pit_div_yield_known`
- 这是诊断版本，用于判断熊市里“已公告”信息是否比“已实施”更有用

### V3: `event_strict_pending_30_monthly`

- 主排序仍用 `pit_div_yield_strict`
- 若分数接近，再用 `pending_div_yield` 做次级排序：
  - 满足 `ann_date <= t`
  - `record_date > t`
  - `ex_date` 为空或 `ex_date > t`
  - `cash_div_tax > 0`
- 只作为 tie-break，不单独加大权重

## 其余框架保持不变

- 月频调仓，信号 `T` 形成，`T+1` 开盘执行
- 30 只等权
- 单行业最多 3 只
- 保留行业内标准化
- 保留质量陷阱过滤
- 不引入新风控、不扩大参数搜索

## 明确限制

1. 2018 年 1 月仍可能存在初始空仓偏差；本轮先如实披露，再决定是否做统一起跑线修复。
2. 行业仍使用 `stock_basic.industry`，不是申万。
3. 停牌时沿用最近价格估值，偏乐观。
4. 这是 2018 单年实验，结论只用于判断下一轮是否值得继续，不宣称普适最优。

## 判定标准

- 先和上一轮最佳 `quality_trap_30_monthly` 比
- 再和 `v6` 的 2018 年结果比
- 优先看：
  - 2018 年总收益
  - 最大回撤
  - 8 月到 12 月月度表现
  - 交易次数是否显著恶化

## 预期

这一轮更合理的目标不是“2018 明显赚钱”，而是：

1. 验证 `dv_ttm` 是否确实不如事件口径稳健
2. 找到更可信的红利 PIT 构造
3. 若仍不如 `v6`，说明独立 long-only 熊市策略的主要短板不在红利口径，而在仓位/空仓机制
