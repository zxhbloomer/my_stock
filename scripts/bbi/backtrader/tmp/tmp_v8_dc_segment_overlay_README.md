# v8 DC Segment Overlay Experiment

## Goal

Test whether 东方财富板块数据 can improve v8 over the strict 2025+ period where both板块行情 and每日成分 are available.

Primary objective: increase return. Secondary objective: avoid lookahead and keep the result easy to reject if it does not beat baseline.

## Data Scope

Required data:

- `099_dc_daily`: 东方财富板块行情, available from 2020-01-02.
- `098_dc_member`: 东方财富板块每日成分, available from 2025-01-02.
- `091_limit_list_d`: 涨跌停/炸板, available from 2020-01-02.

Experiment window:

- Start: `2025-01-02`
- End: latest completed trading day in v8 data, excluding current date if incomplete.

Known source-data notes:

- `083_moneyflow_cnt_ths` has verified source-empty dates and is not a required dependency here.
- `132_sw_daily` has source-side historical gaps and is not used in this experiment.

## Design

The experiment does not change official v8 files. It monkeypatches v8 scoring/add logic in `tmp` only.

Segment features are computed from `099_dc_daily`:

- `ret_5`
- `ret_20`
- `ret_60`
- `amount_rank_pct`
- `drawdown_20`
- `segment_score`
- `segment_crash`
- `segment_mainline`

Stock exposure is computed from `098_dc_member` for the exact signal date. A stock can belong to many segments; its exposure uses the strongest available segment for score boost and any crash segment for risk blocking.

## Variants

- `baseline_2025_replay`: v8 replay from 2025-01-02.
- `dc_segment_score_boost`: add small bounded score boost from strongest segment.
- `dc_segment_no_add_on_crash`: block add buys when any segment exposure is crash.
- `dc_segment_no_buy_on_crash`: remove crash-exposed candidates before new buys.
- `dc_segment_mainline_boost_no_crash`: boost mainline exposure and block crash exposure.

## Progress

- [x] Data completeness checked.
- [x] Unit tests written and red-checked.
- [x] Segment library implemented.
- [x] Experiment runner implemented.
- [x] 2025+ variants run.
- [x] HTML report generated and opened.
- [x] Merge recommendation written.

## Recommendation

This experiment produced a positive 2025+ result:

- `baseline_2025_replay`: total return 76.91%, max drawdown -26.68%.
- `dc_segment_no_buy_on_crash`: total return 106.00%, max drawdown -21.52%.
- `dc_segment_mainline_boost_no_crash`: total return 119.65%, max drawdown -22.77%.

The strongest variant combines:

1. Block new buys when any same-day `signal_date` DC segment exposure is in crash state.
2. Add a small bounded boost when the candidate has mainline DC segment exposure.

Do not merge directly yet. Recommended next step is robustness:

- Run sensitivity around `segment_score >= 0.75`, `seg_ret_20 <= -0.08`, `seg_dd_20 <= -0.12`, and score boost weight.
- Verify month-by-month that improvement does not come from one accidental trade.
- Consider copying the winning experiment into a v9 candidate only after robustness passes.

## QA Lookahead Review

Independent QA review found no clear price-data lookahead: v8 uses the prior
trading day as `signal_date` and trades on the next trading day's open, while
`099_dc_daily` segment features use only the signal day and prior history.

The main risk was `098_dc_member`: same-day segment membership may be a
point-in-time/publication-timing leak if the historical membership is revised
after the signal can be formed. A conservative `member_lag_days=1` variant was
added so the signal day uses the previous available membership snapshot.

Lag1 validation result:

- `dc_segment_no_buy_on_crash_lag1`: total return 139.23%, max drawdown -24.11%.
- `dc_segment_mainline_boost_no_crash_lag1`: total return 139.33%, max drawdown -24.11%.

This reduces the PIT concern because the conservative lagged-membership variants
still beat both `baseline_2025_replay` and the same-day membership variants.
It still should not be merged straight into v8: the next gate is monthly
robustness and a full 2018-2026 replay with the overlay active only from 2025.

## Full-Cycle Active-From-2025 Validation

Runner: `tmp_v8_dc_segment_full_cycle_experiment.py`.

This replay starts from 2018-01-02 with the original v8 state path. The DC
segment overlay is disabled before 2025-01-02 and uses `098_dc_member` lag1
after activation. The end date is fixed at 2026-05-22 to exclude the current
date.

| variant | total_return_pct | annual_return_pct | max_drawdown_pct | 2025_return_pct | 2025_to_end_pct | trades |
|---|---:|---:|---:|---:|---:|---:|
| baseline_full_cycle | 208.83 | 14.39 | -29.80 | 3.26 | 20.99 | 750 |
| no_buy_on_crash_lag1_active2025 | 248.56 | 16.05 | -29.80 | 24.94 | 36.56 | 662 |
| mainline_boost_no_crash_lag1_active2025 | 245.66 | 15.93 | -29.80 | 25.04 | 35.42 | 688 |

Full-cycle result supports advancing `no_buy_on_crash_lag1_active2025` as the
cleaner v9 candidate: it improves total return and the weak 2025 calendar year
while reducing trade count, without increasing full-cycle max drawdown.


## Run Result

| variant | total_return_pct | annual_return_pct | max_drawdown_pct | trades |
|---|---:|---:|---:|---:|
| baseline_2025_replay | 76.91 | 51.03 | -26.68 | 219 |
| dc_segment_score_boost | 67.49 | 45.17 | -26.68 | 203 |
| dc_segment_no_add_on_crash | 94.07 | 61.48 | -26.70 | 236 |
| dc_segment_no_buy_on_crash | 106.00 | 68.60 | -21.52 | 123 |
| dc_segment_mainline_boost_no_crash | 119.65 | 76.60 | -22.77 | 124 |

## Run Result

| variant | total_return_pct | annual_return_pct | max_drawdown_pct | trades |
|---|---:|---:|---:|---:|
| baseline_2025_replay | 76.91 | 51.03 | -26.68 | 219 |
| dc_segment_score_boost | 67.49 | 45.17 | -26.68 | 203 |
| dc_segment_no_add_on_crash | 94.07 | 61.48 | -26.70 | 236 |
| dc_segment_no_buy_on_crash | 106.00 | 68.60 | -21.52 | 123 |
| dc_segment_mainline_boost_no_crash | 119.65 | 76.60 | -22.77 | 124 |
| dc_segment_no_buy_on_crash_lag1 | 139.23 | 87.85 | -24.11 | 149 |
| dc_segment_mainline_boost_no_crash_lag1 | 139.33 | 87.90 | -24.11 | 147 |
