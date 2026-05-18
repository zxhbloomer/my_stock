# v5 Downtrend Buy Filter Experiment

## Goal

Improve v5 return by blocking new buys when an individual stock is in a quantified downtrend.

The experiment stays in `scripts/bbi/backtrader/tmp`, does not modify production v5 files, and does not use git.

## Progress

- 2026-05-17: Started from the requested rule: downtrend stocks should not be bought.
- 2026-05-17: Used `tavily-search` only for web evidence.
- 2026-05-17: Read v5 prepare/backtest scripts and existing tmp evolution experiments.
- 2026-05-17: Read `docs/tushare/接口清单.md` and v5 data preparation queries.
- 2026-05-17: Requested expert reviews for strategy integration, Tushare data suitability, and backtest QA.
- 2026-05-17: First full run showed strict slope/structure downtrend filters blocked candidates but did not change actual v5 trades.
- 2026-05-17: Added earlier weakness variants because the strict downtrend definitions are too late for v5's already-strong candidate set.

## External Evidence

Web sources support these assumptions:

- A downtrend is commonly defined by lower highs and lower lows.
- A downward-sloping moving average or linear-regression slope indicates bearish trend direction.
- Buying stocks below a downward-sloping long moving average is usually a counter-trend trade, not a trend-following entry.

Sources searched:

- StockCharts ChartSchool: linear-regression slope is rise-over-run; positive slope indicates uptrend, negative slope indicates downtrend.
- All Star Charts: lower lows/lower highs below a downward-sloping long moving average indicate a downtrend; stock purchases in that environment are counter-trend.
- Wealthsimple / BetterTrader / LiteFinance: downtrend structure is lower highs plus lower lows.

## Data Design

Use only v5's existing prepared panel for the first implementation:

- `063_stk_factor_pro`: already supplies `open`, `high`, `low`, `close`, `open_qfq`, `close_qfq`, `bbi_qfq`, `amount`, `circ_mv`, `adj_factor`, `turnover_rate`, `volume_ratio`.
- `029_stk_limit`, `030_suspend_d`, `004_stock_st`, `088_top_list`: already integrated into v5 filters.
- `137_idx_factor_pro`: already supplies market index data for regime filters.

Do not add `moneyflow`, `cyq_perf`, or new Tushare tables in this experiment. Those datasets can be useful later, but they update after close and must be shifted before trading decisions.

## Algorithm Design

Add downtrend features to a copy of v5 `panel.parquet` before running the tmp experiment.

Slope filters:

```text
ma60 = rolling mean(close_qfq, 60)
ma120 = rolling mean(close_qfq, 120)
ma60_slope_20 = pct_change(ma60, 20) / 20
ma120_slope_30 = pct_change(ma120, 30) / 30
```

Structure filters:

```text
high_63 = rolling max(close_qfq, 63)
low_63 = rolling min(close_qfq, 63)
prev_high_63 = high_63 shifted by 63 trading days
prev_low_63 = low_63 shifted by 63 trading days
lower_high_63 = high_63 < prev_high_63
lower_low_63 = low_63 < prev_low_63
```

Downtrend definitions:

```text
slope_downtrend =
  close_qfq < ma120
  AND ma60 < ma120
  AND ma120_slope_30 < 0

structure_downtrend =
  lower_high_63
  AND lower_low_63
  AND close_qfq < ma60

strict_downtrend =
  slope_downtrend
  AND structure_downtrend

strong_downtrend =
  close_qfq < ma120
  AND ma20 < ma60
  AND ma60 < ma120
  AND ma60_slope_20 < -0.001
  AND ma120_slope_30 < -0.0005
```

## Experiment Cases

- `baseline_v5`: original v5, with an assertion that results match v5 output.
- `block_slope_downtrend`: block candidates where `slope_downtrend` is true.
- `block_structure_downtrend`: block candidates where `structure_downtrend` is true.
- `block_strict_downtrend`: block only when both slope and structure agree.
- `block_strong_downtrend`: block only clearly steep long downtrends.
- `block_slope_or_structure`: block if either algorithm flags downtrend.
- `block_early_weakness`: block candidates below MA20 with falling MA20 and negative 21-day return.
- `block_mid_weakness`: block candidates below MA60 with falling MA60 and negative 63-day return.
- `block_bbi_breakdown`: block candidates below BBI with falling MA20 and negative 21-day return.
- `block_ma20_rollover`: block candidates below MA20 while MA20 is below MA60 and falling.

## Review Notes

Design reviewer role:

- Favor tmp monkeypatch/wrapper over production v5 edit until a case beats v5.
- Use the previous trading day's `signal_panel`, as v5 already does, to avoid lookahead.
- Track how many baseline buys would have been blocked by each definition.

Data reviewer role:

- First pass should use existing v5 panel and avoid new post-close data.
- Future data candidates must be shifted: `moneyflow`, `cyq_perf`, `cyq_chips`.

QA reviewer role:

- Unit tests should cover slope calculation, structure detection, candidate filtering, and baseline matching.
- Backtest must compare full period plus 2018, 2022, 2024, 2025, and 2026.

## Success Criteria

Primary:

- Full-period total return and annual return exceed v5.
- Full-period max drawdown does not worsen by more than 3 percentage points.
- Baseline result exactly matches current v5 `summary.json`.

Secondary:

- 2018 and 2022 do not degrade materially.
- 2025 and 2026 improvement is not bought by unacceptable drawdown.
- Trade count and blocked-buy diagnostics are explainable.

## Frontend/Report Consideration

No frontend changes are needed for this tmp experiment. If a case wins, production v5 should add report columns for downtrend-filter counts and blocked definitions so the HTML report explains why candidates were skipped.

## Run Results

Commands run:

```powershell
python -m py_compile scripts\bbi\backtrader\tmp\v5_downtrend_filter_experiment.py
python -m unittest scripts\bbi\backtrader\tmp\test_v5_downtrend_filter.py -v
python -X utf8 scripts\bbi\backtrader\tmp\v5_downtrend_filter_experiment.py
```

Outputs:

- `scripts/bbi/backtrader/tmp/v5_downtrend_filter_output/results.csv`
- `scripts/bbi/backtrader/tmp/v5_downtrend_filter_output/summary.md`

Final full-period result after review fixes:

| case | total | annual | max dd | Calmar | 2018 | 2022 | 2024 | 2025 | 2026 | trades | blocked |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| block_early_weakness | 214.56% | 14.68% | -30.61% | 0.4795 | -25.71% | -11.67% | -4.06% | 34.13% | 4.97% | 782 | 32206 |
| baseline_v5 | 140.92% | 11.08% | -31.18% | 0.3554 | -27.49% | -14.68% | -3.03% | 14.22% | 1.38% | 632 | 0 |
| block_bbi_breakdown | 99.04% | 8.57% | -32.58% | 0.2631 | -23.96% | -12.04% | -4.06% | -4.52% | 18.89% | 839 | 28053 |
| block_bbi_breakdown_initial_only | 98.44% | 8.54% | -32.85% | 0.2598 | -23.96% | -12.04% | -4.47% | -4.53% | 18.96% | 841 | 28053 |
| block_early_weakness_initial_only | 76.42% | 7.02% | -39.90% | 0.1760 | -25.71% | -13.30% | -7.17% | 17.49% | -4.42% | 872 | 32206 |
| v4 production baseline | 118.02% | 9.76% | -46.31% | 0.2108 | - | - | - | - | - | 642 | - |

Interpretation:

- The strict long downtrend definitions (`slope_downtrend`, `structure_downtrend`, `strict_downtrend`, `strong_downtrend`) did not affect actual v5 trades.
- The earlier weakness definition did affect trade selection and improved full-period return, annual return, Calmar, 2018, 2022, 2025, and 2026.
- 2024 worsened from `-3.03%` to `-4.06%`; this is a residual trade-off to review before production integration.
- The clean initial-entry-only early weakness filter did not work: full-period return fell to `76.42%` and max drawdown worsened to `-39.90%`.
- The winning `block_early_weakness` case is a full buy-candidate filter. It affects both initial buys and add-buys, which matches a broad "do not buy/add weak downtrend stocks" rule, but it should not be described as initial-entry-only.
- Loading `bbi_qfq` fixed the BBI breakdown case; that variant underperformed v5.
- Yearly rows are calendar-slice diagnostics recalculated from each year's first NAV row. They are not an exact attribution of the full-period total return.
