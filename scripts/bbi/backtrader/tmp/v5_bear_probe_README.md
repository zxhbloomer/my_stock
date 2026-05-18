# v5 Bear Probe Evolution Experiment

## Progress

- 2026-05-16: Started from the current v5 bear-regime question.
- 2026-05-16: Used `tavily-search` only for web evidence.
- 2026-05-16: Read `docs/tushare/接口清单.md` for usable data candidates.
- 2026-05-16: Design review requested from a quant-strategy expert subagent.

## Evidence

Web sources found by `tavily-search` support these working assumptions:

- Bear-market stock chasing has lower reliability; position sizing and risk control matter more than simply relaxing entry.
- Trend following commonly uses moving averages and market breadth to distinguish systemic drawdowns from noise.
- Market breadth is useful because it measures broad participation, not only index level.

Relevant Tushare data candidates:

- Already used in v5: `stk_factor_pro`, `stk_limit`, `suspend_d`, `stock_st`, `top_list`, index factor data.
- Worth future data-engineering checks: `moneyflow`, `moneyflow_mkt_dc`, `moneyflow_hsgt`, `cyq_perf`, `cyq_chips`, `index_dailybasic`, `sw_daily`, `ths_daily`, `limit_list_d`, `limit_step`.
- This experiment does not add new database tables. It only uses v5 output parquet files and the same columns v5 already trusts.

## Design

Goal: test whether v5 can improve profit by allowing strictly limited bear-market probing without weakening deep-bear defense.

Baseline behavior:

- v5 blocks all new buys when market regime is `bear`.
- Existing losing positions exit after a confirmed bear state.
- Profitable holdings are not force-liquidated.

Experiment behavior:

- Keep the original v5 baseline unchanged for comparison.
- In `deep_bear`, continue blocking buys.
- In `bear_repair` or ordinary bear, allow small initial buys only if candidates are much stronger than normal v5 entries.
- Do not add to existing positions while market regime is `bear`.
- Cap bear-regime exposure by case, so the experiment tests controlled risk rather than opening the gate.

Regime buckets:

```text
deep_bear:
  market_dd_252 <= -20% OR breadth_above_bbi <= 20%

bear_repair:
  market_regime == bear
  market_dd_252 > -20%
  breadth_above_bbi >= configured threshold
  market_ma120_slope_20 is not collapsing

bear:
  market_regime == bear and not deep_bear
```

Candidate hardening:

```text
above_ratio_63 >= configured threshold
above_ratio_126 >= configured threshold
ret_63 >= configured threshold
ret_126 >= configured threshold
hot_money_risk_hits <= configured threshold
recent_limit_down_20 == 0
volatility_63 <= cross-section configured quantile
pullback_63 <= configured threshold
```

## Cases

- `baseline_v5`: original v5.
- `bear_probe_10_no_add`: non-deep bear probe, probe-origin exposure <= 10%, no add-buys.
- `bear_probe_20_no_add`: non-deep bear probe, probe-origin exposure <= 20%, no add-buys.
- `bear_probe_10_strict_pullback`: 10% no-add probe plus deeper pullback requirement.
- `bear_probe_10_relaxed`: 10% no-add probe with looser strength and hot-money gates.
- `bear_probe_20_relaxed`: 20% no-add probe with looser strength and hot-money gates.

## Run Notes

- 2026-05-16 first run: strict cases allowed 181 probe days but produced 0 probe buys because the first implementation incorrectly counted all holdings against the probe cap.
- 2026-05-16 second run: fixed probe-origin exposure accounting. Current output has real probe trades, but every bear-probe variant underperforms baseline v5.

## Success Criteria

Primary:

- Full-period total return and annual return exceed v5.
- Full-period max drawdown does not worsen by more than 3 percentage points.

Secondary:

- 2018 and 2022 do not degrade materially.
- 2025 and 2026 improvement cannot be bought by an unacceptable 2018/2022 loss.
- Baseline result must match `scripts/bbi/backtrader/v5/output/summary.json`.

## Frontend/Report Consideration

There is no interactive frontend in this tmp experiment. The reporting surface is `summary.md` plus `results.csv`. If a candidate wins, a later production integration should update v5 HTML report labels and reason mapping so users can inspect bear-probe entries separately.

## Capacity Follow-up

- 2026-05-16: Bear probe produced real trades after correcting probe-origin exposure accounting, but all variants underperformed v5. Started separate capacity experiment because v5 baseline holds ~34% average cash and may under-reinvest profits.
