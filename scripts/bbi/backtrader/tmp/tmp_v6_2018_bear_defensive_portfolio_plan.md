# tmp_v6 2018 独立熊市防御组合计划

1. 复用 `v6` 的面板与交易口径，单独实现一个月频防御组合临时脚本。
2. 用 `daily_basic` 和 `fina_indicator` 补充红利、估值、质量字段。
3. 用 `ann_date` backward merge 做财务 PIT 对齐。
4. 增加最小测试：
   - 财务 backward merge
   - 防御评分方向
   - 月频调仓日期识别
5. 运行 2018 回测，提取 `v4/v5/v6` 的 2018 基线。
6. 生成简单 HTML 报告，按年度、月度展示差异，并自动打开。
7. 在 README 记录进展和结论。
