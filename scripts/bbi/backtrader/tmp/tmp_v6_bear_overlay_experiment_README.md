# tmp_v6 熊市仓位 overlay 实验进度

目标：只把熊市仓位信号叠加到 v6 每日收益，不改变 v6 选股，用于判断空仓/降仓机制是否值得合并。

- 2026-05-19 15:15:30 开始：读取 v6 NAV 和 hysteresis_fast_reentry 熊市仓位信号。
- 2026-05-19 15:15:30 完成 overlay 序列 rows=2021 avg_effective_exposure=56.73%。
- 2026-05-19 15:15:30 完成报表：D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v6_bear_overlay_experiment_output\report.html

## 设计 review

- 专家角色：量化风控专家。
- 判断：本实验应定位为“v6 风险暴露 overlay”，不是替代 v6 的新选股策略。
- 依据：Tavily 复核的公开资料更支持趋势跟随、战术配置、风险叠加在熊市中控制风险暴露；本地数据也显示收益改善主要来自空仓/降仓。
- 关键约束：target_exposure 必须 T-1 生效，避免同日信号同日收益前视。

## 开发 review

- 已检查：overlay 使用 `effective_exposure = target_exposure.shift(1)`，当日收益只乘以前一交易日仓位。
- 已修正：月度收益表从“月初到月末”改为“上月末到本月末”，更适合月度比较。
- 不足：当前 overlay 是收益缩放模型，暂未模拟真实减仓/加仓交易成本、滑点、涨跌停无法成交。
- 合并建议：不要直接替换 v6；建议下一步做“v6 原交易执行 + overlay 调仓执行版”，验证交易成本后再考虑合并。
