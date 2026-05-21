# tmp_v7 极端熊市保险丝实验进度

目标：不改 v7 正式代码，只在 v7 判熊且风险极端时清仓/禁买，验证能否保住 v6 牛市收益并减少熊市亏损。

设计 review：量化风控专家建议不要再用 20/50/100 阶梯仓位，因为上一轮全周期显著拖累牛市；本轮只测极端 risk_off。
开发 review：数据 QA 要求交易日 T 只能使用 T-1 signal_date 的 risk_off 信号；脚本通过动态加载 v7 内存副本实现，不修改 v7 正式代码。

- 2026-05-21 14:19:35 开始：加载 v7 本地 panel/market 数据。
- 2026-05-21 14:19:37 数据完成：panel_rows=9282309 market_rows=2272 end=2026-05-18。
- 2026-05-21 14:19:37 读取 v4 输出基线。
- 2026-05-21 14:19:37 读取 v5 输出基线。
- 2026-05-21 14:19:37 读取 v6 输出基线。
- 2026-05-21 14:19:37 读取 v7 输出基线。
- 2026-05-21 14:19:37 运行 case=v7_baseline。
- 2026-05-21 14:20:46 运行 case=v7_extreme_risk5。
- 2026-05-21 14:22:00 运行 case=v7_extreme_risk6。
- 2026-05-21 14:23:18 运行 case=v7_extreme_dd20_only。
- 2026-05-21 14:24:31 运行 case=v7_extreme_breadth_crash_only。
- 2026-05-21 14:25:43 运行 case=v7_extreme_probe_block_only。
- 2026-05-21 14:26:57 完成：报告 D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_extreme_risk_off_output\report.html
