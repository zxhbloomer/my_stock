# v6 Warning Regime Evolution Plan

1. 写测试：预熊信号由历史回撤、MA120 和市场宽度触发；熊市时不重复标记 warning。
2. 实现 tmp 实验脚本，复用 v6 回测引擎和交易函数。
3. 运行单元测试和 py_compile。
4. 运行全周期回测，输出 results.csv、README、HTML。
5. 打开 HTML 报表，给出是否合并建议。
