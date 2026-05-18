# v6 Uptrend Evolution Experiment Plan

Goal: test whether requiring buy candidates to be in a programmable uptrend improves money-making performance versus v4, v5, and current v6.

Design review:
- Quant expert review recommends three fixed variants: `price_trend_only`, `price_plus_relative_strength`, and `market_regime_adaptive`.
- The rule must use only the signal date panel. v6 trades on the next trading day, so no same-day close-to-same-day trade.
- Do not use unshifted post-close data such as moneyflow or cyq_perf in this experiment.
- Keep the experiment isolated under `scripts/bbi/backtrader/tmp`; do not change v6 production code.

Data:
- Reuse `scripts/bbi/backtrader/v6/output/panel.parquet`.
- Reuse `scripts/bbi/backtrader/v6/output/market_index.parquet`.
- Compare against existing `v4/output`, `v5/output`, and `v6/output`.
- Tushare candidates reviewed from `docs/tushare/接口清单.md`: `063_stk_factor_pro`, `029_stk_limit`, `080_moneyflow`, `061_cyq_perf`, `027_daily_basic`, and index data. This experiment uses only existing v6 fields from `063_stk_factor_pro` and existing market index data.

Definitions:
- `price_trend_only`: `close_qfq > ma60`, `ma20 > ma60`, `ma60_slope_20 > 0`.
- `price_plus_relative_strength`: price trend plus `ret_60 > market_ret_60` and `rps_126 >= 0.70`.
- `market_regime_adaptive`: bull uses moderate uptrend, neutral uses stricter uptrend, bear requires strong trend if v6 market gate allows it.

Steps:
1. Add failing tests for feature calculation, variant filtering, and baseline comparison loading.
2. Implement isolated experiment script.
3. Run tests.
4. Run experiment.
5. Generate compact HTML comparison by summary, year, and month.
6. Open the HTML report.
7. Record outcome and merge recommendation in README.

