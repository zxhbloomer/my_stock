# tmp_v2 Bull Pullback BBI Experiment

## 工作推进
- 使用 Superpowers 流程：头脑风暴、计划、TDD、设计评审、开发、运行验证。
- Tavily 搜索支持：pullback 在上升趋势中常被视为买点候选；移动均线可作支撑/确认；趋势交易顺主趋势。
- 设计评审专家建议：先只测 `bull_reclaim` 与 `non_bear_reclaim`，不要混入 v6 排名增强。
- 开发范围：只写入 `scripts/bbi/backtrader/tmp`。

## 专家意见
设计专家认为：修正后的理论方向合理，pullback 应只在趋势支持时测试；`bull_reclaim` 最干净，`non_bear_reclaim` 是对照但可能混入震荡 whipsaw。已按建议去掉 v6 排名叠加，先验证基础信号。

## 结果摘要
| strategy            |        final_nav |   total_return_pct |   annual_return_pct |   max_drawdown_pct |   calmar_ratio |   avg_cash_pct |   avg_holdings |   trade_records |   win_rate_pct |   avg_hold_days |   signal_days_capacity_available |   bull_signal_days |   neutral_signal_days |   blocked_buy_signals |
|:--------------------|-----------------:|-------------------:|--------------------:|-------------------:|---------------:|---------------:|---------------:|----------------:|---------------:|----------------:|---------------------------------:|-------------------:|----------------------:|----------------------:|
| v4                  |      1.0901e+06  |           118.02   |              9.7629 |           -46.3096 |         0.2108 |       nan      |       nan      |             642 |       nan      |        nan      |                              nan |                nan |                   nan |                   nan |
| v5                  |      1.20461e+06 |           140.922  |             11.0811 |           -31.1754 |         0.3554 |       nan      |       nan      |             632 |       nan      |        nan      |                              nan |                nan |                   nan |                   nan |
| v6                  |      1.57282e+06 |           214.563  |             14.679  |           -30.6143 |         0.4795 |       nan      |       nan      |             782 |       nan      |        nan      |                              nan |                nan |                   nan |                   nan |
| tmp_v2_bull_reclaim     | 335755           |           -32.8489 |             -4.1634 |           -79.419  |        -0.0524 |        55.8048 |         2.2212 |            2103 |        26.5968 |          4.7417 |                              636 |                636 |                     0 |                    59 |
| tmp_v2_non_bear_reclaim |  23432.3         |           -95.3135 |            -27.8788 |           -96.1919 |        -0.2898 |        32.8068 |         2.9709 |            2955 |        27.661  |          4.5261 |                             1132 |                694 |                   437 |                   148 |

## 初步建议
- 本轮最佳净值策略：v6，总收益 214.56%。
- 是否合并：只有 tmp_v2 明显超过 v6 且回撤恶化不超过 3 个百分点，才进入合并候选；否则保留为失败/观察实验。
- 比较口径：tmp_v2 是 qfq 价格口径的独立 tmp 策略系统，v4/v5/v6 是既有完整系统输出；此处用于收益/风险方向性比较，不等同于完全相同的撮合账本。

