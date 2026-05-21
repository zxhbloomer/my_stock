# v6 Warning Regime Evolution Design

## Brainstorming Expert
2018 年 3 月下旬才确认熊市不算晚于 20% 回撤定义，但作为风控开始偏晚。新增 warning 状态，不等同熊市，只提前降低新买风险。

## Data Expert
本轮只使用 v6 已准备的上证指数、市场宽度和股票技术面字段。Tushare 061/080/138 暂不新增，避免盘后数据时点问题和归因混乱。

## Quant Design Expert
新增 `warning_market_ok`。当市场尚未确认熊市，但出现 60/120/252 日回撤、跌破 MA120 且 MA120 转弱、或市场宽度低于 45% 时，进入预熊。预熊期不加仓，只允许减小首买金额，必要时提高回撤要求。

## Review Expert
实验只写 tmp，不改 v4/v5/v6 生产代码；baseline_v6 必须复现 v6 summary；重点检查 warning 只使用 signal_date 及以前数据。
