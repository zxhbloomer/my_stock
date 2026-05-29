# v8 BBI 强势股轮动策略

v8 是 v7 的独立复制版本，已合入 `tmp` 中验证过的“纯牛市小额最后加仓”“长期低效持仓退出”和“DC 赛道真实强度轻量加分”逻辑。

## 当前状态

- 基础策略：沿用 v7 的弱市低波动动量过滤、牛市提前买入、熊市过滤和熊市小仓位试探逻辑。
- 新增逻辑：`纯牛市小额最后加仓`。
  - 单票原始 4 档：8 万、6 万、4 万、2 万。
  - 新增第 5 档：5 万。
  - 第 5 档触发条件：信号日 `market_regime == "bull"`、持仓已到第 4 档、持仓仍在候选榜、浮盈达到 50%。
  - 震荡市和熊市不触发第 5 档额外加仓。
- 合入依据：`tmp_v7_pure_bull_winner_add_output` 显示该方案总收益从 v7 的 302.16% 提升到 331.17%，最大回撤仍为 -29.80%；后续 `truncation_recompute` 对 6 笔实际额外加仓做了截断重算，6/6 可复现。
- 风险说明：截断重算证明的是 6 笔成交在截断数据下可复现，不等同于完整无未来函数证明；参数邻域和成本压力仍建议继续在 `tmp` 验证。
- 统计说明：`pure_bull_extra_add_signals` 表示达到第 5 档尝试检查的次数，包含非牛市被拒情形；`pure_bull_extra_add_fills` 才是实际成交次数。
- 新增逻辑：`长期低效持仓退出`。
  - 触发条件：持仓交易日数达到 231、信号日浮盈不大于 0%、且持仓股票跌出当日 v8 候选榜前 20。
  - 执行口径：使用上一交易日信号数据判断，次日开盘卖出。
  - 合入依据：`tmp_v8_rank_stale_exit_output` 的二维实验显示，浮盈阈值 `<= 0%` 且 8-11 个月区间优于 v8；`231d` 总收益最高，但仅触发 1 笔，后续仍需跟踪样本稳定性。
  - 统计说明：`rank_stale_exit_signals` 为信号次数，`rank_stale_exit_fills` 为实际成交次数。
- 新增逻辑：`DC 赛道真实强度轻量加分`。
  - 作用位置：候选股先经过原有 `DC segment crash filter`，再根据股票真实所属赛道的 `segment_score` 做轻量加分。
  - 计算口径：沿用 v8 已有的 `DC_SEGMENT_MEMBER_LAG_DAYS=1` 成分滞后口径，使用信号日可见的赛道特征；单票取所属赛道中的最高 `segment_score`。
  - 参数：`DC_SEGMENT_SCORE_WEIGHT = 0.05`，即 `score += 0.05 * clip(segment_score, -2, 2)`。
  - 合入依据：`tmp_v8_dc_segment_stability_output` 显示 `w0p05_full` 在完整区间稳定优于 formal v8；全区间总收益约从 `283.96%` 提升到 `289.34%`，年化约从 `17.37%` 提升到 `17.56%`，最大回撤维持在 `-29.80%`。
  - 稳定性说明：`w0p05_full`、`w0p08_full`、`w0p10_full` 结果基本一致，`w0p12_full` 开始明显劣化，因此正式版采用更保守的 `0.05`。
- 隔离要求：v8 不 import v7，不读取 v7 的输出文件。
- 输出目录：所有 v8 产物只写入 `scripts/bbi/backtrader/v8/output`。
- 数据目录：`config.py` 使用 `Path(__file__).parent / "output"`，因此运行在 v8 时只使用 v8 本地 output。
- 数据库完整性：`10_prepare_data.py` 开始拉取数据前会校验 `063_stk_factor_pro`、`029_stk_limit`、`137_idx_factor_pro`，并在 DC overlay 启用时从 `2025-01-02` 起校验 `098_dc_member`、`099_dc_daily`；失败会停止 prepare。`20_run_backtest.py` 仍保留 DC overlay 运行前校验，作为第二道防线。

## 运行

```powershell
cd scripts/bbi/backtrader/v8
python -X utf8 10_prepare_data.py
python -X utf8 20_run_backtest.py
python -X utf8 30_generate_report.py
```

## 最新正式回测

本次正式输出来自 `scripts/bbi/backtrader/v8/output/summary.json`：

| 指标 | 数值 |
|------|------|
| 回测周期 | 2018-01-02 ~ 2026-05-28 |
| 初始资金 | 500,000 |
| 最终净值 | 1,961,566.03 |
| 总收益率 | 292.3132% |
| 年化收益 | 17.6588% |
| 最大回撤 | -29.8042% |
| Calmar | 0.5925 |
| 交易记录数 | 683 |
| 纯牛市第 5 档实际加仓 | 4 |
| 长期低效持仓退出成交 | 1 |
| DC 赛道过滤候选拦截 | 2,199 |

`30_generate_report.py` 生成的 HTML 报告包含最新候选股票 Top 30，展示排名、股票代码、名称、价格、当前仓位、建仓日期、卖出日期和交易原因；月度收益表的周内信息使用候选股真实所属 DC 赛道热点，便于核对最新候选池、持仓状态和赛道暴露。

## 验证

```powershell
python -X utf8 -m py_compile scripts\bbi\backtrader\v8\10_prepare_data.py scripts\bbi\backtrader\v8\20_run_backtest.py scripts\bbi\backtrader\v8\30_generate_report.py
python -X utf8 -m unittest discover -s scripts\bbi\backtrader\v8 -p "test*.py" -v
python -X utf8 -m unittest scripts.bbi.backtrader.tmp.test_v8_prepare_db_completeness -v
python -X utf8 -m unittest scripts.bbi.backtrader.tmp.test_v8_pure_bull_merge_contract -v
```

其中 `v8/test*.py` 是从历史版本继承的行为测试；`tmp/test_v8_prepare_db_completeness.py` 是 prepare 前数据库完整性规则测试；`tmp/test_v8_pure_bull_merge_contract.py` 是本次 v8 合入的隔离与第 5 档合约测试。

回测后核对核心指标：

```powershell
Get-Content scripts\bbi\backtrader\v8\output\summary.json |
  Select-String "total_return_pct|max_drawdown_pct|trade_records|pure_bull_extra_add_fills|rank_stale_exit_fills|dc_segment_candidate_blocks"
```

当前目标口径以后续最新 v8 回测输出为准；重点核对 `total_return_pct` 是否接近 `292.31%`、`max_drawdown_pct` 是否仍接近 `-29.80%`，以及 `pure_bull_extra_add_fills`、`rank_stale_exit_fills` 是否符合预期。

## 后续演化原则

后续如果继续扩大仓位或调整参数，应先在 `tmp` 中独立回测验证，再明确合入 v8。v8 正式代码不能读取其他版本的净值、交易记录、调仓日志或其他输出文件。
