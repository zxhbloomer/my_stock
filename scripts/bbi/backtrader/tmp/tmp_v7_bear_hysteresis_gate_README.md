# tmp_v7 熊市仓位状态机实验进度

目标：不改 v7 正式代码，验证 v7 熊市判断触发后接入 hysteresis_fast_reentry 仓位状态机是否值得合入。

- 2026-05-21 13:57:47 开始：加载 v7 本地 panel/market 数据。
- 2026-05-21 13:57:49 数据完成：panel_rows=9282309 market_rows=2272 end=2026-05-18。
- 2026-05-21 13:57:49 读取 v6 输出基线。
- 2026-05-21 13:57:49 运行 case=v7_baseline。
- 2026-05-21 13:58:56 运行 case=v7_bear_hysteresis_gate。
- 2026-05-21 14:00:05 运行 case=v7_bear_hysteresis_defense_only。
- 2026-05-21 14:01:24 完成：报告 D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_bear_hysteresis_gate_output\report.html
