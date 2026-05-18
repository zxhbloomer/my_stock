# v6 Weak Uptrend Gate Plan

Date: 2026-05-17

## Goal

Test whether v6 can improve return and drawdown by applying an uptrend confirmation only in weak or neutral market conditions, instead of requiring uptrend confirmation all the time.

## Web Evidence Checked With Tavily

- Uptrend is commonly quantified by price above rising moving averages, moving-average alignment, higher relative strength, and closeness to a 52-week high.
- Minervini-style trend templates use 50/150/200-day moving averages, rising long moving average, 52-week high/low position, and RS >= 70.
- Academic trend-following literature supports moving-average and time-series momentum filters, but papers also note regime dependence.
- China A-share papers are mixed: short-horizon momentum can exist, while medium/long-horizon momentum often weakens or reverses. This argues against copying US-style full-time momentum screens blindly.

## Design Review Notes

Expert role: quantitative strategy designer.

The previous full-time uptrend filter underperformed v6, so this design keeps v6 unchanged in confirmed bull markets. v6 already blocks new buys in confirmed bear markets, so this experiment does not override the bear no-entry rule. The new gate is only applied when the market regime is neutral, unknown, or recently bearish.

Second expert review added a correction: the first draft was still too strict and could conflict with v6's pullback-entry edge. Therefore the run will include lighter weak/neutral confirmations, plus one isolated high-risk bear exception variant for observation.

## Variants

1. `neutral_price_gate`
   - Bull: keep v6 candidates unchanged.
   - Neutral or unknown: require `close_qfq > ma60_qfq`, `ma20_qfq > ma60_qfq`, `ma60_slope_20 > 0`.
   - Bear: v6 already blocks entries before candidate scoring.

2. `neutral_rs_gate`
   - Bull: keep v6 candidates unchanged.
   - Neutral or unknown: require the price gate plus `ret_63 > market_ret_60`, `rps_126 >= 0.70`, `high_pos_252 >= 0.75`.

3. `post_bear_strict_gate`
   - Bull: keep v6 candidates unchanged.
   - Neutral or unknown after a recent bear regime: require strict trend structure: `close > ma60 > ma120 > ma200`, positive `ma120` and `ma200` slopes, `rps_126 >= 0.80`, `high_pos_252 >= 0.80`.
   - Neutral without recent bear: use `neutral_rs_gate`.

4. `neutral_weak_price_confirm`
   - Bull: keep v6 candidates unchanged.
   - Neutral or unknown: require `close_qfq > ma20_qfq`, `ma20_slope_10 > 0`, `ret_21 > 0`.
   - Purpose: light confirmation that should not overly reject v6 pullback entries.

5. `neutral_rs_confirm`
   - Bull: keep v6 candidates unchanged.
   - Neutral or unknown: require `ret_63 > market_ret_60` or `rps_126 >= 0.60`.
   - Purpose: test relative strength with a softer threshold than the previous full-time experiment.

6. `weak_regime_no_new_low`
   - Bull: keep v6 candidates unchanged.
   - Neutral or unknown: require `range_pos_63 >= 0.35` or `high_pos_63 >= 0.75`.
   - Purpose: avoid buying names still breaking down, while not requiring 252-day high proximity.

7. `bear_exception_uptrend`
   - Experimental only.
   - Converts v6 bear no-entry into a strict exception: in bear regime require `close_qfq > ma60_qfq`, `ma60_slope_20 > 0`, `rps_126 >= 0.80`, `high_pos_252 >= 0.75`.
   - Risk: this changes v6 bear-block behavior and must not be merged without separate robustness tests.

## Data

- Use existing v6 `output/panel.parquet` and `output/market_index.parquet`.
- Compute `ma60/120/150/200`, slopes, 252-day high/low position, and RPS locally from `close_qfq` and existing return columns.
- Do not use unshifted post-close data such as moneyflow or cyq_perf in this iteration.
- Tushare `063_stk_factor_pro` has technical factors and v6 already has `ma20_qfq`; additional rolling windows can be computed from `close_qfq`.

## Tests

- Feature calculation must not use future rows for past dates.
- Bull regime must leave v6 candidates unchanged.
- Neutral regime must filter weak price trends.
- Neutral RS gate must filter stocks without relative strength.
- Strict post-bear gate must keep only strong aligned trends.
- Baseline outputs for v4/v5/v6 must load successfully.

## Merge Criteria

Recommend merging only if the new best variant improves v6 annualized return or final NAV while not materially worsening maximum drawdown and monthly stability. If the best result is below v6, keep as research output only.
