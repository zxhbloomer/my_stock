# v8 BBI 强势股轮动策略

v8 是 v7 的独立复制版本，已合入 `tmp` 中验证过的“纯牛市小额最后加仓”和“长期低效持仓退出”逻辑。

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
- 隔离要求：v8 不 import v7，不读取 v7 的输出文件。
- 输出目录：所有 v8 产物只写入 `scripts/bbi/backtrader/v8/output`。
- 数据目录：`config.py` 使用 `Path(__file__).parent / "output"`，因此运行在 v8 时只使用 v8 本地 output。
- 数据库完整性：`10_prepare_data.py` 开始拉取数据前会校验 `063_stk_factor_pro`、`029_stk_limit`、`137_idx_factor_pro`，只检查 SSE 开市日是否完全缺失，以及单日行数是否低于前一有效交易日的 80%；失败会停止 prepare。

## 运行

```powershell
cd scripts/bbi/backtrader/v8
python -X utf8 10_prepare_data.py
python -X utf8 20_run_backtest.py
python -X utf8 30_generate_report.py
```

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
  Select-String "total_return_pct|max_drawdown_pct|trade_records|pure_bull_extra_add_fills|rank_stale_exit_fills"
```

当前目标口径以后续最新 v8 回测输出为准；重点核对 `max_drawdown_pct`、`pure_bull_extra_add_fills` 和 `rank_stale_exit_fills` 是否符合预期。

## 后续演化原则

后续如果继续扩大仓位或调整参数，应先在 `tmp` 中独立回测验证，再明确合入 v8。v8 正式代码不能读取其他版本的净值、交易记录、调仓日志或其他输出文件。
