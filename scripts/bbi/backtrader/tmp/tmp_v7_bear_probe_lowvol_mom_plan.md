# tmp_v7 Bear Probe Lowvol Momentum Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. 本计划不操作 git。

**Goal:** 测试 v7 熊市反弹确认窗口中的低波动量小仓位试探，争取改善 2018 且保留全周期收益。

**Architecture:** 动态加载 v7，不改正式 v7；复用上一轮 weak_lowvol_mom 过滤；额外注入 refined bear probe 开关、候选过滤和仓位 cap。

**Tech Stack:** Python, pandas, local v7 backtest outputs.

---

### Task 1: 测试
- [x] 写 `test_tmp_v7_bear_probe_lowvol_mom.py`。
- [x] 验证 RED：模块不存在时失败。

### Task 2: 实现
- [x] 新增实验脚本。
- [x] 实现 refined probe open、target amount、candidate filter。
- [x] 注入 v7 run_backtest。

### Task 3: 验证
- [ ] 跑测试和 py_compile。
- [ ] 跑全周期回测。
- [ ] 生成 HTML 报表。
- [ ] 做 QA review 和合并建议。
