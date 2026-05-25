# v8 Theme Overlay Experiment

## Goal

Improve v8 return by adding a conservative A-share annual theme overlay without changing official v8 files.

Primary objective: return improvement. Secondary objective: keep drawdown and lookahead risk visible.

## Scope

- Work directory: `scripts/bbi/backtrader/tmp`
- Base strategy: `scripts/bbi/backtrader/v8`
- No git operations.
- Experiment output: `scripts/bbi/backtrader/tmp/tmp_v8_theme_overlay_output`
- Report: `scripts/bbi/backtrader/tmp/tmp_v8_theme_overlay_output/report.html`

## Research Notes

- Tavily search confirmed industry momentum is a documented anomaly. The core reference is Moskowitz and Grinblatt, "Do Industries Explain Momentum?"
- Tavily search also confirmed investor attention is commonly proxied by search/news/hot-list style data. In this first experiment, attention data is not used for trading because local hot-list history is incomplete.
- The first tradable overlay uses structured local data only:
  - `132_sw_daily`: Shenwan industry daily bars.
  - `131_index_member_all`: point-in-time-limited latest industry mapping. This is not ideal for historical membership drift, so the first version treats industry membership as a stable research proxy and records this limitation.
  - `091_limit_list_d`, `083_moneyflow_cnt_ths`, `085_moneyflow_ind_dc`: reserved for diagnostics/reporting before becoming trading signals.

## Design

### Expert Role: Quant Design Reviewer

Checks:
- Theme signal must be known by the decision time.
- Avoid using post-close data for same-day open trades.
- Prefer broad, stable industry-level features before concept-level features.
- Keep the first overlay as a ranking adjustment, not a hard allocation engine.

### Trading Logic

Base v8 keeps its market regime, stop-loss, limit-down, weak-market low-vol momentum filter, and pure bull extra add logic.

The experiment wraps `v8.score_candidates()`:

1. Let v8 create normal candidates.
2. Attach each stock's Shenwan L1 industry.
3. For the signal date, attach industry theme features:
   - 21-day industry return.
   - 63-day industry return.
   - 20-day industry moving-average slope.
   - 21-day industry drawdown.
4. Convert industry features to daily cross-sectional z-scores.
5. Add a bounded theme adjustment to the v8 stock score.
6. Penalize theme crash industries, but do not hard-block them in the first pass.

### Lookahead Rule

v8 trades on `date` using `signal_date = previous trading day`.

The overlay may use industry close and breadth data on `signal_date` because it is only used for the next trading day's open. It must not use data from `date` or later.

Post-close moneyflow or hot-list data is not used for trading in this first implementation. If later added, it must follow the same signal-date-only rule.

## Implementation Plan

1. Add unit tests for theme feature construction and score adjustment.
2. Implement a small library with pure functions.
3. Add a tmp experiment runner that imports v8, patches score ranking, runs backtest, and writes outputs.
4. Add a tmp report generator for annual/monthly comparison against v4, v5, v6, v7, v8.
5. Run tests, run experiment, inspect results.
6. Invite code-review expert to review implementation and report risks.
7. Open the HTML report.

## Progress

- [x] v8 reviewed.
- [x] Tushare interface inventory reviewed.
- [x] Tavily research run for industry momentum and investor attention.
- [x] Unit tests written and red-checked.
- [x] Overlay library implemented.
- [x] Experiment runner implemented.
- [x] Report generated.
- [x] Code review completed.
- [x] Final recommendation written.

## Run Result

Completed at 2026-05-23.

| variant | total_return_pct | annual_return_pct | max_drawdown_pct | trades | notes |
|---|---:|---:|---:|---:|---|
| baseline_v8_replay | 208.83 | 14.39 | -29.80 | 750 | Reproduces current v8 output. |
| theme_score_boost | 204.87 | 14.21 | -29.80 | 791 | Theme score boost did not improve return. |
| theme_ebb_filter_candidates | 149.23 | 11.50 | -37.49 | 716 | Candidate filtering harmed both return and drawdown. |
| theme_ebb_no_add | 203.22 | 14.14 | -29.80 | 779 | Add blocking did not improve return. |
| theme_ebb_filter_and_no_add | 149.23 | 11.50 | -37.49 | 716 | Same as candidate filtering because filtered candidates already block adds. |

Preliminary recommendation: do not merge this theme overlay into v8. Continue only as research, preferably with point-in-time industry membership or a different theme definition.

## Review Findings

- Quant design review rejected first-pass theme chasing as a primary merge candidate because older tmp evidence showed申万主线加分跑输基线.
- Code review found a high-severity point-in-time risk: `131_index_member_all` is a latest static mapping, not historical membership.
- Report logic was corrected to compare theme variants against same-run `baseline_v8_replay`, not possibly stale v8 output.
- Annual/monthly report logic was corrected to use previous period-end NAV to current period-end NAV.

Final recommendation: do not merge. The next useful evolution is either:

1. Build a point-in-time industry membership dataset before retesting industry theme overlay.
2. Research a non-industry theme proxy based on daily limit-up/limit-down and concept heat, but only after enforcing strict data availability by year.


- Experiment run completed and HTML report generated.
