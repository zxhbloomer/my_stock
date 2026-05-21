# tmp_v7 Weak Market Quality Momentum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 本计划按用户要求不操作 git。

**Goal:** 在 tmp 中验证弱熊市低波动量过滤是否优于 v7 baseline。

**Architecture:** 动态加载 v7 `20_run_backtest.py`，不改正式 v7；对 `score_candidates` 后的候选增加 case 级过滤；生成全周期、年度、月度 HTML 对比。

**Tech Stack:** Python, pandas, v7 backtest module, local CSV/Parquet outputs.

---

### Task 1: 测试先行
- [x] 新增 `test_tmp_v7_weak_market_quality_momentum.py`。
- [x] 验证 RED：目标实验模块不存在时测试失败。

### Task 2: 实验脚本
- [x] 新增 `tmp_v7_weak_market_quality_momentum_experiment.py`。
- [x] 实现 FIP、market_ret_63、弱熊市场候选过滤。
- [x] 动态加载 v7 并在内存注入过滤逻辑。

### Task 3: 回测和报表
- [ ] 运行测试。
- [ ] 运行全周期回测。
- [ ] 生成并打开 HTML 报表。
- [ ] 记录 README 进度和 review 结论。
