# tmp_v7 弱市/熊市价值质量辅助实验

目标：在不修改正式 v7 的前提下，验证“PB/PE 估值 + ROE/ROA/现金流质量 + 股息率”是否适合作为 v7 弱市/熊市辅助过滤或加分，而不是替代 v7 主策略。

设计 review：
- 量化研究员：PB+ROE 是公开研究中常见的价值质量框架，但低 PB 单因子可能是价值陷阱，必须叠加盈利质量、现金流、负债和趋势确认。
- 数据工程师：`027_daily_basic` 可提供 PB/PE/股息率，`042_fina_indicator` 可提供 ROE/ROA/经营现金流/负债率；财务指标必须按 `ann_date + 1 day` 后才允许使用。
- 风控专家：不改牛市/正常市场；只在 v7 已判断的弱 neutral 或 bear_probe 候选中加价值质量约束。
- 状态机设计：沿用 v7 已有 `ma120/ma120_slope_20/dd_252/breadth_above_bbi`；熊市为 252 日回撤 <= -20% 或跌破 MA120 且斜率和市场广度转弱；牛市为站上 MA120、斜率向上、回撤较浅且广度 >= 55%；弱市为 neutral 但回撤 <= -10% 且广度 <= 55%。

Tavily 复核：
- 熊市常见定义包含从高点下跌约 20%；趋势判断常用均线、动量和市场广度，和 v7 状态机一致。
- PB-ROE 策略支持低估值+高盈利质量，但不能单独替代趋势主策略。

进度：
- 2026-05-22 09:11:04 开始设计-开发-回测闭环。
- 2026-05-22 09:11:08 加载 v7 panel rows=9,282,309。
- 2026-05-22 09:11:08 读取 daily_basic 信号日估值数据。
- 2026-05-22 09:12:08 daily_basic rows=9,187,379。
- 2026-05-22 09:12:08 读取 fina_indicator 财务指标数据。
- 2026-05-22 09:12:13 fina_indicator rows=204,863。
- 2026-05-22 09:13:11 完成信号日财务特征准备，不合并到全量 panel。
- 2026-05-22 09:14:53 完成 weak_vq_rerank20：total_return=241.71%，trades=593。
- 2026-05-22 09:16:35 完成 weak_vq_rerank30：total_return=241.45%，trades=595。
- 2026-05-22 09:19:21 完成 weak_vq_top70_rerank20：total_return=1.47%，trades=772。
- 2026-05-22 09:22:19 完成 bear_probe_vq_top70：total_return=268.82%，trades=813。
- 2026-05-22 09:25:21 完成 weak_plus_bear_vq_top70：total_return=138.76%，trades=788。
- 2026-05-22 09:25:21 生成 HTML 报表：D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_regime_value_quality_overlay_output\report.html
- 2026-05-22 09:31:00 QA review：单元测试覆盖弱市/熊市触发、正常市场不干预、ann_date+1 PIT；未发现明显未来函数。
- 2026-05-22 09:31:00 结论：bear_probe_vq_top70 几乎不伤收益但提升有限；weak_vq_rerank20/30 降低交易但全周期收益低于 v7，暂不合并。
