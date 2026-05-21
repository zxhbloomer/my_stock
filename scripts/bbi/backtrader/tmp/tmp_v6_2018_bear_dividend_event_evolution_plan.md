# tmp_v6 2018 独立熊市分红事件进化计划

1. 新建 `tmp_v6_2018_bear_dividend_event_evolution.py`，基于上一轮独立熊市防御进化脚本做最小增量修改。
2. 新建 `test_tmp_v6_2018_bear_dividend_event_evolution.py`。
3. 先写失败测试：
   - 同一 `ts_code + end_date` 多次公告时，只保留当前时点最新已知状态
   - `ex_date` 严格口径不能在除息日前计入分红
   - `ann_date` 口径可以在公告后、除息前计入分红
   - pending 口径只在 `record_date` 之前有效
4. 实现 `041_dividend` 加载、PIT 事件展开与三个 case：
   - `event_ex_date_strict_30_monthly`
   - `event_ann_date_known_30_monthly`
   - `event_strict_pending_30_monthly`
5. 跑单测和 `py_compile`。
6. 运行 2018 回测，输出各 case 的 `nav.csv`、`trades.csv`、`results.csv`。
7. 生成简单 HTML：
   - case 结果
   - 和 `v4`/`v5`/`v6`/上一轮最佳 `quality_trap_30_monthly` 的年度、月度对比
   - 是否建议合并
   - 局限与下一步
8. 自动打开 HTML。
9. 做一次代码 review，总结未来函数风险、1 月空仓偏差、是否值得继续合并。
