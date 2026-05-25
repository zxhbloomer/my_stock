# v7 pure bull winner add progress

## Assumptions

- Only `market_regime == "bull"` may trigger the new extra winner add.
- `neutral` and `bear` must not trigger extra winner buys. They still carry any extra bull position already bought, so later path is not mathematically identical to v7.
- Formal `v4`, `v5`, `v6`, and `v7` files are not modified.
- This experiment writes only under `scripts/bbi/backtrader/tmp`.

## External Review

- Momentum profitability can vary by market state; Cooper, Gutierrez, and Hameed (2004) is a common reference for market-state-dependent momentum.
- Momentum and trend following can suffer state-dependent crashes, so local backtest evidence is required before merging.
- Pyramiding should be limited to winners; adding to idle cash without a winner condition is not the experiment.

## Design Review

- Quant expert: expand only the fifth add step, not number of holdings.
- Risk expert: keep baseline 500k cap for normal v7 behavior; allow expanded cap only for bull extra winner adds.
- Engineering expert: inject into a copied tmp experiment runner, not official strategy files.

## Plan

- [x] Brainstorm state-separated position logic.
- [x] Use Tavily search to review market-state and momentum definitions.
- [x] Record this README before implementation.
- [x] Write tests for case parameters, bull-only gate, exposure cap, and source patch safety.
- [x] Implement three pure-bull winner-add cases.
- [x] Development review: strict `step_index == 4`, neutral/bear gate closed, normal v7 exposure path unchanged.
- [x] Run unit tests and py_compile.
- [x] Run full backtest and generate HTML report.
- [x] Runtime review: all `pure_bull_extra_add` fills occurred in `bull`; audit CSVs are written beside the report.
- [x] Open the report automatically.

## Result Snapshot

- v7 baseline reproduce: total return 302.16%, max drawdown -29.80%.
- Pure bull winner 300k: total return 269.51%, max drawdown -29.80%, extra adds 8.
- Strict pure bull winner 300k: total return 310.61%, max drawdown -29.80%, extra adds 6.
- Pure bull small final add: total return 331.17%, max drawdown -29.80%, extra adds 6.

## Merge View

- Candidate: `纯牛市小额最后加仓`.
- Reason: improves total return over v7 with no observed max drawdown deterioration in this backtest.
- Caution: only 6 extra fills, and bull extra positions carry into later neutral/bear periods, so it needs robustness checks by year/regime before touching formal v7.
- 2026-05-23 16:27:23 开始运行纯牛市赢家加仓实验。
- 2026-05-23 16:27:25 加载 v7 panel rows=9,282,309。
- 2026-05-23 16:28:19 完成 当前v7复现：total_return=302.16%，max_dd=-29.80%，trades=765，extra_adds=0。
- 2026-05-23 16:29:13 完成 纯牛市赢家30万：total_return=269.51%，max_dd=-29.80%，trades=698，extra_adds=8。
- 2026-05-23 16:30:08 完成 严格纯牛市赢家30万：total_return=310.61%，max_dd=-29.80%，trades=702，extra_adds=6。
- 2026-05-23 16:31:05 完成 纯牛市小额最后加仓：total_return=331.17%，max_dd=-29.80%，trades=717，extra_adds=6。
- 2026-05-23 16:31:05 生成 HTML 报表：D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_pure_bull_winner_add_output\report.html
- 2026-05-23 16:31:05 设计 review：专家角色确认本轮只改 bull 的第5次赢家加仓，不增加持股数。
- 2026-05-23 16:31:05 开发 review：检查项包括 neutral/bear 禁止额外加仓、普通 v7 仓位上限不变、严格回撤门控、额外加仓统计。
- 2026-05-23 16:35:05 开始运行纯牛市赢家加仓实验。
- 2026-05-23 16:35:06 加载 v7 panel rows=9,282,309。
- 2026-05-23 16:36:02 完成 当前v7复现：total_return=302.16%，max_dd=-29.80%，trades=765，extra_adds=0。
- 2026-05-23 16:36:58 完成 纯牛市赢家30万：total_return=269.51%，max_dd=-29.80%，trades=698，extra_adds=8。
- 2026-05-23 16:37:54 完成 严格纯牛市赢家30万：total_return=310.61%，max_dd=-29.80%，trades=702，extra_adds=6。
- 2026-05-23 16:38:48 完成 纯牛市小额最后加仓：total_return=331.17%，max_dd=-29.80%，trades=717，extra_adds=6。
- 2026-05-23 16:38:49 生成 HTML 报表：D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_pure_bull_winner_add_output\report.html
- 2026-05-23 16:38:49 设计 review：专家角色确认本轮只改 bull 的第5次赢家加仓，不增加持股数。
- 2026-05-23 16:38:49 开发 review：检查项包括 neutral/bear 禁止触发额外买入、普通 v7 仓位上限不变、严格回撤门控、额外加仓统计。
- 2026-05-23 16:38:49 最终 review：bull 额外仓位会被带入后续 neutral/bear，因此本轮结论是买入动作 bull-only，不是后续路径完全等同 v7。
