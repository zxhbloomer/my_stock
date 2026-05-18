# tmp_v3_slope_regime_repair Plan

## Goal

Use v6 PIT output to test whether slope/regime repair signals can improve return without adding lookahead risk.

## Research Basis

- Trend following/time-series momentum can work over persistent trends, but reacts slowly near turning points.
- Momentum crash literature shows bear-market rebounds can reverse classic momentum leadership.
- Changepoint/fast-reversion research supports combining slow trend state with faster repair signals around turning points.
- Tushare data used here is limited to already prepared v6 PIT daily data: `stock_basic`, `stock_st`, `stk_factor_pro`, `stk_limit`, `top_list`, and `idx_factor_pro`. No post-close extra table is introduced.

## Expert Review

- Quant researcher: focus first on bear repair because v6 showed a concrete empty-position period in 2018-09 to 2019-01.
- Risk reviewer: bear repair must use small exposure caps and previous-day signals only.
- Data reviewer: do not add `moneyflow`, `cyq_perf`, or financial tables in this experiment because they add disclosure/shift complexity.
- Engineering reviewer: implement under `scripts/bbi/backtrader/tmp`; do not modify official v6 code.

## Experiment Cases

1. `baseline_v6`: current v6 PIT result from output.
2. `bear_repair_20`: allow new buys during bear repair with 20% max exposure.
3. `bear_repair_40`: allow new buys during bear repair with 40% max exposure.
4. `bear_repair_40_bull_accel`: bear repair plus bull/neutral healthy acceleration threshold relaxation.
5. `bear_repair_40_blowoff_guard`: bear repair plus no-buy guard for extreme stock blowoff.

## Bear Repair Signal

Computed on `signal_date` only:

- `market_regime == "bear"`
- `market_dd_252` has recovered at least 5 percentage points from its trailing 60-day minimum.
- `ma120_slope_20` is better than 10 trading days ago.
- `breadth_above_bbi` improved by at least 15 percentage points versus 10 trading days ago.
- 20-day index return is positive.

## Trading Rules

- When official v6 blocks buys only because `market_regime == "bear"`, allow buys if bear repair is true.
- In bear repair, max total exposure is capped by case: 20% or 40% of initial capital.
- In bear repair, buy at most 2 holdings and disable add buys.
- Use existing v6 candidate scoring and filters.
- Trade execution remains T open using T-1 signal.

## Success Criteria

- Higher total return and annual return than v6 PIT baseline.
- Max drawdown should not worsen by more than 5 percentage points.
- Report must show annual and monthly differences.
- If improved only by materially increasing drawdown, do not recommend merge.
