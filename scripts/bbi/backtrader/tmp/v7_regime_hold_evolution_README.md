# v7 Regime Hold Evolution

## Goal

提升收益优先，但必须用可复现回测验证。tmp 实验阶段不改 v4/v5/v6/v7 正式代码，不操作 git；用户确认后，才将通过验证的最小思想单独落到 v7。

## Expert Workflow

1. 量化定义专家：用 Tavily 复核趋势跟踪、止损、行业轮动/主线定义。
2. 设计专家：把想法压成可回测规则，先做状态化止损和持有保护，暂不新增复杂板块数据。
3. 开发专家：在 `scripts/bbi/backtrader/tmp` 实现实验脚本和单元测试。
4. 代码审阅专家：检查未来函数、状态判断、回测对比和报表逻辑。
5. 运行确认专家：运行测试、回测、生成 HTML，与 v4/v5/v6/v7 对比。

## Tavily Notes

- Trend following / time-series momentum: 文献和综述均把趋势定义为过去收益或价格相对均线的延续；月度/中期频率通常比日频噪声更低。参考：
  - https://openaccess.city.ac.uk/id/eprint/17842/8/BLACKBOX%20%20%20SSRN-id2126476.pdf
  - https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf
  - https://quantpedia.com/strategies/time-series-momentum-effect
- Stop loss: 趋势策略在拐点处容易受损，止损可以控回撤，但过密交易和过度参数化容易过拟合。
- Sector rotation / 主线: 行业轮动通常基于行业相对强弱、过去收益、经济周期或成分股动量；第一轮实验不直接接板块表，先验证持有逻辑是否有价值。参考：
  - https://www.johnrothe.com/p/the-alpha-in-sector-rotation-a-research-driven-approach
  - https://quantpedia.com/strategies/sector-momentum-rotational-system
  - https://bigquant.com/wiki/doc/DlXVSO3ZVu

## Design Review

设计专家判断：当前 v7 的主要收益来自 bull/neutral 买入，bear 已基本被阻断；因此第一轮提升收益应优先减少 bull 和弱势修复期的过早卖出，而不是扩大熊市交易。

### Variant A: baseline_v7

直接读取 v7 输出，作为基准。

### Variant B: bull_wide_stop

- `bull` 状态下止损从 `-5%` 放宽到 `-8%`。
- 其他状态不变。
- 目标：验证牛市宽止损是否能提升收益且不明显扩大回撤。

### Variant C: bull_weak_repair_hold

- `bull` 状态下止损 `-8%`。
- `weak_repair` 状态下，如果个股仍是强趋势，止损 `-7%`。
- `weak_repair` 定义：
  - `market_regime == neutral`
  - `market_dd_252 <= -0.10`
  - `breadth_above_bbi <= 0.55`
  - `breadth_change_5 > 0`
- 强趋势持有保护：
  - `above_ratio_63 >= 0.70`
  - `above_ratio_126 >= 0.55`
  - `close_qfq > bbi_qfq`
  - `ret_63 > 0`
  - `recent_limit_down_20 == 0`
  - `hot_money_risk_hits < 2`

## Implementation Plan

1. 写单元测试覆盖 `weak_repair`、状态化止损、强趋势持有保护。
2. 实现实验脚本 `v7_regime_hold_evolution.py`，复用 v7 数据和工具函数，只在 tmp 中运行。
3. 回测 baseline_v7、bull_wide_stop、bull_weak_repair_hold。
4. 生成年度/月度对比、summary 对比、HTML 报表。
5. 自动打开 HTML 报表。

## Progress

- 2026-05-22: 完成 Tavily 复核和第一轮设计。
- 2026-05-22: 第一轮回测完成。`baseline_v7_replay` 与 v7 输出完全一致；`bull_wide_stop` 和 `bull_weak_repair_hold` 均显著弱于 v7，设计专家否决“放宽亏损止损”。
- 2026-05-22: 第二轮转向“不放宽止损，只优化牛市入场/排序”。“牛市提前买入”总收益 302.1605%，高于 v7 的 268.8279%，最大回撤同为 -29.8042%；评分重排类变体弱于 v7。
- 2026-05-22: 用户确认“记住这个节点，然后按建议开始测试”。节点记录：只测试“牛市提前买入”思想，目标是把它作为 v7 最小补丁单独验证；不合并宽止损、不合并评分重排。
- 2026-05-22: 正式 v7 最小补丁验证完成：只改变 bull 入场阈值，止损、neutral、bear 不变；v7 回测总收益 302.1605%，最大回撤 -29.8042%。

## Current Result

| strategy | total_return_pct | annual_return_pct | max_drawdown_pct | calmar_ratio | trade_records |
|---|---:|---:|---:|---:|---:|
| 牛市提前买入 | 302.1605 | 18.0703 | -29.8042 | 0.6063 | 765 |
| v7 | 268.8279 | 16.8572 | -29.8042 | 0.5656 | 813 |
| baseline_v7_replay | 268.8279 | 16.8572 | -29.8042 | 0.5656 | 813 |

## Merge Recommendation

初步建议只考虑合并“牛市提前买入”的思想：在市场状态为牛市时，把初始买入回撤阈值从 v7 的 `-0.04/-0.026` 调整为 `-0.025/-0.012`。不要合并宽止损和评分重排类变体。

合并前必须再做：

1. 代码审阅确认没有未来函数或非 bull 状态误改。
2. 单独做“牛市提前买入”的更小补丁和 v7 单元测试。
3. 复跑 v7 全流程并确认 HTML 报表。
