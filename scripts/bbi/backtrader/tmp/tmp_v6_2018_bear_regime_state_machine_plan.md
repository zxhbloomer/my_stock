# tmp_v6 2018 熊市状态机实验计划

1. 新建 `tmp_v6_2018_bear_regime_state_machine.py`，基于上一轮防御股票池脚本做最小增量改造。
2. 新建 `test_tmp_v6_2018_bear_regime_state_machine.py`。
3. 先写失败测试：
   - 状态分类函数能正确区分 `risk_on / neutral / risk_off`
   - 仓位映射函数能输出正确目标暴露
   - 行业限额选择仍然生效
4. 实现市场状态特征：
   - 指数 MA60 偏离
   - 指数 120 日回撤
   - 市场广度
   - 资金流弱确认
5. 实现 3 个状态机 case：
   - `state_machine_base`
   - `state_machine_strict`
   - `state_machine_breadth`
6. 跑单测和 `py_compile`。
7. 运行 2018 回测，输出各 case 的 `nav.csv`、`trades.csv`、`results.csv`。
8. 生成 HTML：
   - 与 `v4`、`v5`、`v6`、上一轮最佳 case 对比
   - 年度、月度
   - 是否建议合并
9. 自动打开 HTML。
10. 做代码 review，总结是否值得继续沿“状态机”进化。
