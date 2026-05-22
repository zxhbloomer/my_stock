# tmp_v7 价值质量低换手实验

目标：在不修改正式 v7 的前提下，验证“PB/PE 估值 + ROE/ROA/现金流质量 + 股息率 + 低换手调仓”是否能保留收益、降低交易频率和改善弱市年份。

设计 review：
- 量化研究员：PB+ROE 是公开研究中常见的价值质量框架，但低 PB 单因子可能是价值陷阱，必须叠加盈利质量、现金流、负债和趋势确认。
- 数据工程师：`027_daily_basic` 可提供 PB/PE/股息率，`042_fina_indicator` 可提供 ROE/ROA/经营现金流/负债率；财务指标必须按 `ann_date + 1 day` 后才允许使用。
- 风控专家：不把 v7 直接改成价值策略，先做 tmp 独立实验；低换手通过月末/季末信号日买入、放宽止损和提高加仓门槛实现。
- 开发 review：单日月末/季末窗口过严，第一轮全周期 0 交易；改为月末最后 5 个信号日、季末最后 8 个信号日，保留低换手但避免完全错过入场。
- 开发 review 2：月末/季末窗口仍 0 交易，补充日频入场版本，用来区分“价值因子无效”和“低换手窗口过窄”。

Tavily 复核：
- PB-ROE 策略研究支持低 PB 与高 ROE 组合，但提示行业/风格切换和价值陷阱风险。
- 红利、低估值、低波动、质量组合常用于稳健/长期配置。

进度：
- 2026-05-21 23:26:01 开始设计-开发-回测闭环。
- 2026-05-21 23:26:03 加载 v7 panel rows=9,282,309。
- 2026-05-21 23:26:03 读取 daily_basic 信号日估值数据。
- 2026-05-21 23:27:22 daily_basic rows=9,181,880。
- 2026-05-21 23:27:22 读取 fina_indicator 财务指标数据。
- 2026-05-21 23:27:25 fina_indicator rows=204,863。
- 2026-05-21 23:28:34 完成信号日财务特征准备，不合并到全量 panel。
- 2026-05-21 23:30:50 完成 vq40_daily_stop10：total_return=-12.38%，trades=565。
- 2026-05-21 23:33:11 完成 vq60_daily_stop12：total_return=76.04%，trades=441。
- 2026-05-21 23:34:34 完成 vq40_monthly_stop10：total_return=-52.25%，trades=357。
- 2026-05-21 23:35:54 完成 vq60_monthly_stop12：total_return=-66.34%，trades=362。
- 2026-05-21 23:37:07 完成 vq60_quarterly_stop12：total_return=1.69%，trades=194。
- 2026-05-21 23:37:07 生成 HTML 报表：D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v7_value_quality_lowturnover_output\report.html
- 2026-05-21 23:45:00 QA review：未发现明显未来函数；补充 ann_date+1 PIT 单元测试；结论仅作为负向 tmp 实验，不建议合并。
