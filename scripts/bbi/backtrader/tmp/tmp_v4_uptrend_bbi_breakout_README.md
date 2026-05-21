# tmp_v4_uptrend_bbi_breakout

## Goal

Validate whether adding explicit BBI breakout confirmation to the existing v6 uptrend logic improves returns versus v4, v5, and v6.

## Design Review

Expert role: quantitative research reviewer.

Decision:

- Reasonable as a hypothesis, not as an assumed improvement.
- Use BBI breakout as a right-side trigger: signal day close crosses above BBI, execute on the next trading day through the existing v6 engine.
- Test both short BBI and mid BBI confirmation.
- Avoid adding moneyflow or cyq data in this round because those are post-close datasets and require a separate T+1 shift design.

## Variants

- `short_bbi_breakout`: close crosses above database BBI, close is at least 0.5% above BBI, and 5-day BBI slope is positive.
- `short_bbi_breakout_trend`: short breakout plus `close > MA20 > MA60`, positive MA20/MA60 slope, positive 60-day return, close near 252-day high.
- `dual_bbi_breakout_trend`: short breakout plus price above self-calculated mid BBI `(MA5+MA10+MA20+MA60)/4` and both BBI slopes positive.
- `adaptive_bbi_breakout_trend`: bull market uses looser trend thresholds, neutral/bear uses stricter relative strength and high-position thresholds.

## Data Notes

- Existing v6 `panel.parquet` is used for stock data.
- Existing v6 `market_index.parquet` is used for market regime.
- Tushare reference from `docs/tushare/接口清单.md`:
  - `daily`, `daily_basic`, `stk_limit`, `suspend_d`, `stock_st`, `stk_factor_pro` are already represented in prepared v6 panel fields.
  - `moneyflow` and `cyq_perf` are candidates for future work only with explicit lagging.

## Progress

- 2026-05-18: Web sources checked with Tavily. BBI breakout definition confirmed as price crossing above BBI with BBI rising, but with known false-signal risk in sideways markets.
- 2026-05-18: Existing v6 engine reviewed. New experiment will monkey-patch `score_candidates` only, preserving v6 execution, cost, limit-up/down, pullback entry gate, and next-day execution behavior.

## Run Result

- Report: `D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v4_uptrend_bbi_breakout_output\report.html`
- Best by final NAV: `v6` final_nav=1416886.56, annual=13.26%, max_dd=-35.56%.
- Merge recommendation is written in the HTML report.

## Review Notes

- Code review found no blocking anti-lookahead issue.
- The experiment is not a pure BBI breakout system. It is v6 candidate selection plus BBI breakout filtering, and v6 pullback entry thresholds still apply.
- The report was updated to state the 0.5% breakout buffer and 5-day BBI slope definition explicitly.

## Run Result

- Report: `D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\tmp_v4_uptrend_bbi_breakout_output\report.html`
- Best by final NAV: `v6` final_nav=1416886.56, annual=13.26%, max_dd=-35.56%.
- Merge recommendation is written in the HTML report.
