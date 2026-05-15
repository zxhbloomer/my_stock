# v4 BBI 2018 熊市研究汇总

## 本轮边界

- 只在 `scripts/bbi/backtrader/tmp` 做实验与记录。
- 未合入 `scripts/bbi/backtrader/v4`。
- 本轮重跑的 `v4_bear_2018_experiment.py` 会导入当前工作树的 `v4/20_run_backtest.py`，因此结果代表“当前工作树 v4 代码”，不是 2026-05-12 旧留档。

## 外部证据

- Faber 的战术资产配置研究使用长期均线过滤风险资产，核心用途是降低深熊市暴露，而不是提高每一段行情的收益。
- Moskowitz、Ooi、Pedersen 的时间序列动量研究显示，跨资产趋势/动量在指数、商品、债券、外汇中存在，适合用于市场状态过滤。
- Hurst、Ooi、Pedersen 的趋势跟踪长期证据显示，趋势跟踪在多个大型危机期表现较好，说明熊市里优先处理市场 beta 是合理方向。
- 中国市场文献提示 A 股存在短期时间序列动量和长期反转，且动量/反转随市场状态变化；因此不能简单把“强势股动量”无条件套到 2018 熊市。
- GitHub 搜索没有发现可直接迁移的 A 股 BBI 熊市策略。可参考的是通用 backtrader/均线/战术配置框架，不应照搬具体参数。

## Tushare 数据优先级

第一轮继续只用现有 v4 数据：

- `063_stk_factor_pro`: 个股 BBI 与技术因子。
- `137_idx_factor_pro`: 上证指数行情、指数 BBI、指数均线。

第二轮再考虑引入：

- `129_index_dailybasic`: 指数估值、换手率、市值，用于估值/活跃度环境。
- `138_daily_info`: 沪深市场每日交易统计，用于全市场成交和市场宽度。
- `080_moneyflow`: 个股资金流向。必须整体后移一日后才能用于次日开盘。
- `073_margin` / `074_margin_detail`: 两融情绪和杠杆收缩，只适合做市场级风险因子。

## 2018 tmp 实验结果

脚本：

```powershell
python -X utf8 scripts/bbi/backtrader/tmp/v4_bear_2018_experiment.py
```

当前工作树 v4 基准：

- 2018 收益：`-31.64%`
- 2018 最大回撤：`-34.34%`

本轮最优：

- `market_gate = ma120`
- `pullback_threshold = -7%`
- 2018 收益：`-7.91%`
- 2018 年化：`-8.01%`
- 2018 最大回撤：`-15.04%`
- 交易记录：`22`
- 市场阻断日：`217`

各类门禁最优对比：

| market_gate | pullback_threshold | 2018 收益 | 最大回撤 | 交易记录 | 市场阻断日 |
|---|---:|---:|---:|---:|---:|
| ma120 | -7% | -7.91% | -15.04% | 22 | 217 |
| ma200 | -15% | -17.62% | -21.03% | 39 | 212 |
| bbi_5_20_60_120 | -8% | -26.17% | -32.51% | 67 | 207 |
| ma120_or_bbi | -8% | -26.17% | -32.51% | 67 | 207 |
| none | -8% | -28.24% | -34.94% | 126 | 42 |

## 全区间复验

脚本：

```powershell
python -X utf8 scripts/bbi/backtrader/tmp/v4_bear_ma120_full_experiment.py
```

全区间结果：

| case | 总收益 | 年化 | 最大回撤 | 平均现金% | 交易数 |
|---|---:|---:|---:|---:|---:|
| current_threshold_5 | 118.02% | 9.76% | -46.31% | 16.23% | 642 |
| ma120_threshold_8 | -18.77% | -2.45% | -60.97% | 26.71% | 544 |
| ma120_threshold_5 | -22.67% | -3.03% | -68.58% | 31.48% | 562 |
| ma120_threshold_7 | -23.55% | -3.16% | -66.40% | 26.99% | 660 |

关键分段：

| case | 2018 收益 | 2019-2021 收益 | 2022 收益 | 2025 收益 |
|---|---:|---:|---:|---:|
| current_threshold_5 | -31.64% | 206.44% | -29.17% | 34.83% |
| ma120_threshold_5 | -10.27% | 53.73% | -39.33% | -6.08% |
| ma120_threshold_7 | -7.91% | 78.56% | -26.37% | 0.58% |
| ma120_threshold_8 | -11.06% | 83.58% | -31.93% | -0.63% |

## 熊市防守期实验

脚本：

```powershell
python -X utf8 scripts/bbi/backtrader/tmp/v4_bear_defense_experiment.py
```

算法：

- 当原 v4 市场过滤触发 `market_5d_drop` 或 `market_20d_drawdown` 时，进入 N 个信号日防守期。
- `block_buys`: 防守期不新开仓，已有持仓仍按当前 v4 规则处理。
- `sell_losers`: 防守期不新开仓，并把浮亏持仓按次日开盘退出；盈利持仓继续按当前 v4 规则处理。

全区间前几名：

| case | mode | 总收益 | 年化 | 最大回撤 | 平均现金% | 交易数 |
|---|---|---:|---:|---:|---:|---:|
| sell_losers30_pb7 | sell_losers | 146.90% | 11.41% | -31.64% | 42.97% | 436 |
| current | current | 118.02% | 9.76% | -46.31% | 16.23% | 642 |
| block30_pb7 | block_buys | 81.44% | 7.38% | -46.01% | 38.51% | 512 |

关键分段：

| case | 2018收益 | 2019-2021收益 | 2022收益 | 2025收益 | 全区间最大回撤 |
|---|---:|---:|---:|---:|---:|
| current | -31.64% | 206.44% | -29.17% | 34.83% | -46.31% |
| sell_losers30_pb7 | -20.30% | 204.36% | -19.31% | 25.94% | -31.64% |
| block40_pb7 | -12.73% | 115.80% | -33.03% | 0.20% | -63.54% |

## 判断

2018 熊市改善最明显的是“上证 120 日均线门禁 + 买入回撤阈值略加深”。它没有把 2018 转正，但把亏损和回撤都大幅压低。

但全区间复验直接否定了“全局 ma120 门禁合入 v4”。它会严重错过 2019-2021 和 2025 的收益，且全区间收益转负、最大回撤反而扩大。

更稳健的结论是：当前 BBI 强势股框架的问题不是个股强弱排序完全失效，而是 2018 这种单边熊市里市场 beta 太强。熊市优化应优先做“熊市识别后临时降风险”，而不是把长期均线门禁无条件套到所有年份。

本轮最值得继续验证的是 `sell_losers30_pb7`：它不是 2018 单年最优，但全区间收益高于当前基线，最大回撤从 `-46.31%` 降到 `-31.64%`，并且 2022 熊市也明显改善。代价是 2025 少赚约 8.89 个百分点，平均现金占比升到约 `42.97%`。

## 不建议现在做的事

- 不建议直接引入资金流、两融、行业资金流。它们都是盘后或滞后数据，先接入会增加未来函数和过拟合风险。
- 不建议直接合入 `ma120`。全区间复验已经显示它不是可接受的全局规则。
- 不建议合入 `block_buys` 系列。它能改善 2018，但全区间收益牺牲过大。

## 下一步建议

1. 围绕 `sell_losers30_pb7` 做更细的邻域实验：防守期 `25/30/35`，回撤阈值 `-6%/-7%/-8%`。
2. 加一组“浮亏退出阈值”：`profit <= 0% / -2% / -3%`，判断是否能减少 2025 少赚。
3. 加一组“防守期结束后恢复条件”：如果上证重新站上 20 日均线或近 5 日转正，提前结束防守期。
4. 只有当邻域实验稳定，再讨论是否合入正式 `v4`。

## 来源

- Faber, M. `A Quantitative Approach to Tactical Asset Allocation`: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2403936_code649342.pdf?abstractid=962461&mirid=1
- Moskowitz, T. J., Ooi, Y. H., Pedersen, L. H. `Time Series Momentum`: https://research-api.cbs.dk/ws/portalfiles/portal/58851003/time_series_momentum_lasse_heje.pdf
- Hurst, B., Ooi, Y. H., Pedersen, L. H. `A Century of Evidence on Trend-Following Investing`: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2993026
- `Time series momentum and contrarian effects in the Chinese stock market`: https://arxiv.org/abs/1702.07374
- `The evolvement of momentum effects in China`: https://centaur.reading.ac.uk/109131
