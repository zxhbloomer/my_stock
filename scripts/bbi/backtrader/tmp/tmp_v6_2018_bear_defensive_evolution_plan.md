# tmp_v6 2018 独立熊市防御策略进化计划

1. 新建 `tmp_v6_2018_bear_defensive_evolution.py`，复用现有独立熊市策略的数据加载与基础回测口径。
2. 新建 `test_tmp_v6_2018_bear_defensive_evolution.py`。
3. 先写失败测试：
   - 行业约束能限制每个行业最多 N 只
   - 行业内 zscore 不把不同行业混在一起
   - 质量陷阱过滤能剔除高股息但低质量股票
4. 实现行业字段加载、行业内特征、多个 case。
5. 跑测试与 `py_compile`。
6. 运行 2018 回测，输出 CSV 和 HTML。
7. HTML 自动打开，包含年度/月度对比、case 结果、行业集中度、建议。
8. 请求代码 review，修正关键问题。

