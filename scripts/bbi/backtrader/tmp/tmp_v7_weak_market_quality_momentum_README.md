# tmp_v7 弱熊市质量动量过滤实验进度

目标：不修改 v7 正式代码，验证弱市/熊市下低波、动量一致性、相对强弱过滤能否减少亏损并保留牛市收益。

- 2026-05-21 16:55:03 完成设计和计划文档。
- 2026-05-21 16:55:05 加载 v7 panel rows=9282309。
- 2026-05-21 16:55:05 开始运行 case=v7_baseline。
- 2026-05-21 16:56:13 完成 case=v7_baseline total=180.0989% max_dd=-35.5607% weak_blocks=0。
- 2026-05-21 16:56:13 开始运行 case=weak_lowvol_mom。
- 2026-05-21 16:57:24 完成 case=weak_lowvol_mom total=268.8279% max_dd=-29.8042% weak_blocks=4445。
- 2026-05-21 16:57:24 开始运行 case=weak_fip_lowvol。
- 2026-05-21 16:58:31 完成 case=weak_fip_lowvol total=106.0932% max_dd=-48.4192% weak_blocks=5988。
- 2026-05-21 16:58:31 开始运行 case=weak_relative_strength。
- 2026-05-21 16:59:38 完成 case=weak_relative_strength total=101.3303% max_dd=-41.0181% weak_blocks=6369。
- 2026-05-21 16:59:38 开始运行 case=weak_combined。
- 2026-05-21 17:00:42 完成 case=weak_combined total=94.2665% max_dd=-42.1395% weak_blocks=7910。
- 2026-05-21 17:00:42 完成报表：D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_weak_market_quality_momentum_output\report.html
- 2026-05-21 17:00:42 已尝试自动打开 HTML 报表。
- 2026-05-21 17:04:34 QA review 后修正报表结论：weak_lowvol_mom 全周期最好，但 2018 未改善，暂不直接合并。
