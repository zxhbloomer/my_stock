# tmp_v7 neutral 拆分与风险预算仓位实验

## 目标

前轮确认：简单 bull 扩仓即使补上降级减仓，仍弱于 v7。关键现象是 v7 的 `neutral` 阶段贡献很强，而扩仓实验破坏了 neutral 复利。本轮按“先拆 neutral，再用风险预算调仓”的理论继续进化。

## 本轮理论

- `neutral` 不是无行情，应拆成更细状态。
- 仓位不应只由 bull/neutral/bear 决定，还应由波动率、策略自身净值回撤共同决定。
- 扩仓不再增加持股数，仍保持 v7 最多 5 只；只调整总风险预算。

## Tavily 复核

- 波动率管理研究指出，权益和动量类策略常在高波动状态下降低风险暴露，在低波动状态提高风险暴露；但过度杠杆和高换手会伤害结果。
- momentum/market state 文献提示，市场状态不能只分 bull/bear；修复、回调、反弹等阶段会显著影响动量收益。
- drawdown 是从高点到后续低点的回撤，适合作为策略自身风险预算的约束。

## Tushare 数据评估

`docs/tushare/接口清单.md` 显示可用数据包括 `daily_basic`、`stk_limit`、`cyq_perf`、`moneyflow`、`index_dailybasic`、`repo_daily`。本轮暂不新增这些数据，原因：

- 本轮问题是仓位状态机，不是选股因子。
- `moneyflow`、`cyq_perf` 属于盘后数据，未来使用必须严格 shift。
- 当前 v7 已有 market、breadth、strategy NAV，足够验证仓位管理假设。

## neutral 拆分定义

基于 v7 已有 `regime_snapshot`：

- `bull`：沿用 v7。
- `bear`：沿用 v7。
- `neutral_up`：neutral 且市场广度 `breadth_above_bbi >= 0.50`，120 日均线 20 日斜率为正，252 日回撤大于 -15%。
- `neutral_repair`：neutral 且广度 5 日改善 `breadth_change_5 >= 0.08`，但尚未满足 `neutral_up`。
- `neutral_down`：neutral 且广度低于 0.45，或 120 日均线斜率为负，或 252 日回撤小于等于 -15%。
- `neutral_chop`：其他 neutral。

## 实验方案

### A. 只审计 neutral 拆分

不改变交易，只看 v7 的收益贡献来自哪个细分状态。

### B. 波动率目标仓位

- 最多 5 只，不增加持股数。
- 以策略净值过去 20 日波动率估计风险。
- 目标年化波动率 18%，仓位系数限制在 0.70 到 1.30。
- 只在 bull / neutral_up / neutral_repair 允许系数高于 1；neutral_down 和 bear 不放大。

### C. 净值曲线风险预算

- 策略回撤小于 5%：允许 1.20 倍基础风险预算。
- 回撤 5%-10%：1.00 倍。
- 回撤 10%-15%：0.80 倍。
- 回撤超过 15%：0.60 倍。
- 仍最多 5 只，不增加持股数。

### D. 组合版

同时满足 volatility target 和 equity curve budget，取二者较小值，避免低波动但策略自身回撤较深时盲目加仓。

## 专家角色设计评审

- 量化研究员：本轮比 bull 扩仓更合理，因为先解释 v7 的 neutral 收益来源，再做仓位预算。
- 风控专家：赞成不增加持股数；最大系数 1.30 保守，避免重复前轮 80%-95% NAV 的错误。
- 数据工程师：不新增盘后数据，降低反向偏差风险；所有状态来自 v7 已有 signal_date 快照。
- 开发审查专家：必须有规则测试，确认 neutral 分类、波动率倍率、回撤倍率、状态门控都符合预期。
- 报表专家：报告展示核心指标、年度/月度、细分状态收益贡献、合并建议。

## 实施计划

1. 写规则测试并确认失败。
2. 实现实验脚本和 HTML 报告。
3. 运行测试和编译检查。
4. 完整回测并对比 v4/v5/v6/v7。
5. 做开发 review 和结果 review。
6. 自动打开 HTML。

## 进度

- 2026-05-23 开始本轮设计；方向为 neutral 拆分、波动率目标、净值曲线风险预算。
- 2026-05-23 15:43:17 开始运行 neutral 拆分与风险预算仓位实验。
- 2026-05-23 15:44:02 开始运行 neutral 拆分与风险预算仓位实验。
- 2026-05-23 15:44:05 加载 v7 panel rows=9,282,309，生成状态细分 rows=2,272。
- 2026-05-23 15:45:10 完成 当前v7复现：total_return=302.16%，max_dd=-29.80%，trades=765，avg_budget=1.00
- 2026-05-23 15:46:11 完成 波动率目标仓位：total_return=149.66%，max_dd=-31.40%，trades=750，avg_budget=0.81
- 2026-05-23 15:47:11 完成 净值曲线风险预算：total_return=99.96%，max_dd=-34.06%，trades=679，avg_budget=0.70
- 2026-05-23 15:48:15 完成 波动率+净值组合预算：total_return=79.92%，max_dd=-39.47%，trades=745，avg_budget=0.65
- 2026-05-23 15:48:15 生成 HTML 报表：D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_neutral_vol_risk_output\report.html
- 2026-05-23 15:48:15 设计 review：专家角色确认本轮先拆 neutral，再测试风险预算，不继续粗暴扩持股数。
- 2026-05-23 15:48:15 开发 review：检查项包括 signal_date 口径、最多5只约束、预算系数门控、状态细分贡献。
- 2026-05-23 15:49:38 开始运行 neutral 拆分与风险预算仓位实验。
- 2026-05-23 15:49:41 加载 v7 panel rows=9,282,309，生成状态细分 rows=2,271。
- 2026-05-23 15:50:41 完成 当前v7复现：total_return=302.16%，max_dd=-29.80%，trades=765，avg_budget=1.00
- 2026-05-23 15:51:42 完成 波动率目标仓位：total_return=149.66%，max_dd=-31.40%，trades=750，avg_budget=0.81
- 2026-05-23 15:52:42 完成 净值曲线风险预算：total_return=99.96%，max_dd=-34.06%，trades=679，avg_budget=0.70
- 2026-05-23 15:53:43 完成 波动率+净值组合预算：total_return=79.92%，max_dd=-39.47%，trades=745，avg_budget=0.65
- 2026-05-23 15:53:43 生成 HTML 报表：D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_neutral_vol_risk_output\report.html
- 2026-05-23 15:53:43 设计 review：专家角色确认本轮先拆 neutral，再测试风险预算，不继续粗暴扩持股数。
- 2026-05-23 15:53:43 开发 review：检查项包括 signal_date 口径、最多5只约束、预算系数门控、状态细分贡献。
- 2026-05-23 结果 review：当前 v7 复现为 302.16% / -29.80%；波动率目标仓位为 149.66% / -31.40%；净值曲线风险预算为 99.96% / -34.06%；组合预算为 79.92% / -39.47%。本轮不建议合并。
- 2026-05-23 归因 review：v7 的收益贡献主要来自 `neutral_down` 与 bull 以外的状态，简单按波动率/净值回撤降低预算会错过大量 v7 原本能抓住的行情。下一步应做失败买入过滤，而不是继续降低或放大总仓。
- 2026-05-23 开发修正：细分状态贡献表从当天状态改为 signal_date 对下一交易日生效的对齐方式，符合 v7 交易口径。
