# 2018 v6 Top20 Evolution Implementation Plan

**Goal:** 解释 v6 为什么错过 2018 非游资非新股 Top20，并验证一个熊市条件放行实验是否改善收益。

**Architecture:** 单个临时模块提供可测试函数，主流程读取现有 v4/v5/v6 输出，生成诊断、回测、对比和 HTML 报告。

**Tasks:**
- 写标准库 unittest 测试：Top20 过滤、漏买原因分类、防御动量打分。
- 实现 `v6_top20_evolution.py`。
- 运行测试。
- 运行实验，生成 CSV/JSON/HTML。
- 打开 HTML。

**No-git:** 不执行 git 命令，不改正式 v4/v5/v6 文件。
