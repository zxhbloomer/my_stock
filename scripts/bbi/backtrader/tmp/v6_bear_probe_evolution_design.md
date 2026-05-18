# v6 Bear Probe Evolution Design

## Brainstorming Expert
熊市买入不能等同抄底。Web 复核支持使用市场宽度修复、均线转强和右侧确认区分熊市反弹与熊末修复。

## Data Expert
本轮使用 v6 已准备的 063 stk_factor_pro 和 137 idx_factor_pro。061 cyq_perf、080 moneyflow、138 daily_info 暂不新增，因为之前相关实验未优于 v6，且盘后数据会增加披露时点和归因复杂度。

## Quant Design Expert
新增 `bear_probe_market_ok` 与 `bear_probe_stock_ok`。只有熊市状态、市场宽度 5 日明显修复、指数站上 MA20 且 MA20 斜率为正，才允许小仓位试探买入。个股必须重新站上 BBI、BBI 斜率转正、5 日收益为正，且没有加速失速/下跌风险。

## Review Expert
实验只写 tmp，不改 v4/v5/v6 生产代码；baseline_v6 必须复现 v6 summary；报表必须包含 v4/v5/v6 和候选策略的年度、月度对比。
