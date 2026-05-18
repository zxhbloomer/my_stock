# v6 Moneyflow/CYQ Evolution Experiment

## Goal

Continue evolving from v6 without modifying production v4/v5/v6 code or output.

Primary goal: improve return. Secondary guardrail: do not worsen max drawdown by more than 3 percentage points versus v6.

## Progress

- 2026-05-17: Started tmp-only evolution from current v6 baseline.
- 2026-05-17: Read `docs/tushare/接口清单.md`; local database contains `080_moneyflow`, `061_cyq_perf`, `027_daily_basic`, board-flow and limit-list tables.
- 2026-05-17: Used `tavily-search` only for external evidence. Search supports volume/money-flow as trend confirmation, but also shows money-flow indicators are noisy and should not be trusted as standalone signals.
- 2026-05-17: Requested strategy and data/QA expert reviews before implementation.
- 2026-05-17: Added TDD tests for post-close feature shifting, baseline preservation, candidate filtering, and score boosting.
- 2026-05-17: Ran full tmp experiment and generated HTML report.

## Data Design

Base strategy data:

- `scripts/bbi/backtrader/v6/output/panel.parquet`
- `scripts/bbi/backtrader/v6/output/market_index.parquet`

Extra Tushare tables:

- `080_moneyflow`: individual stock money flow.
- `061_cyq_perf`: daily chip/winner-rate metrics.

Anti-lookahead rule:

- `moneyflow` and `cyq_perf` are post-close data.
- The experiment merges raw rows by `ts_code/trade_date`, then applies per-stock `shift(1)` before calculating 5/20-day rolling features.
- No backfill or forward fill is used.
- This means `signal_date=T` can only see moneyflow/cyq values from `T-1` and earlier.

## Cases

| case | design |
|---|---|
| `baseline_v6` | current v6, must exactly match v6 `summary.json` |
| `flow_net_ma5_positive` | keep candidates with shifted 5-day average net flow amount > 0 |
| `flow_big_ma5_positive` | keep candidates with shifted 5-day average large+extra-large net flow amount > 0 |
| `flow_net_rank_top70` | keep top 70% by shifted 5-day net-flow rate inside the candidate set |
| `cyq_winner_mid` | keep candidates with winner rate 35%-85% and price above weighted average cost |
| `flow_score_boost_015` | add 0.15 * zscore(shifted net-flow-rate MA5) to v6 score |
| `flow_big_score_boost_015` | add 0.15 * zscore(shifted big-flow-rate MA5) to v6 score |
| `flow_and_cyq_combo` | require positive net flow, positive big flow, winner rate 35%-85%, and price above weighted average cost |

## Expert Review

Strategy review:

- `flow_score_boost` is the least destructive first-round candidate.
- Hard filters can easily narrow the candidate set too much.
- `cyq_winner_mid` has high overfitting risk because it mixes chip state and price trend.
- All candidates must compare against v6, not v5.

Data/QA review:

- Do not call v6 `main()` in the experiment because it writes production v6 output.
- Import v6 functions and write only to tmp output.
- Shift moneyflow/cyq fields before any rolling, rank, threshold, or zscore calculation.
- Track feature coverage because moneyflow/cyq may have missing rows or shorter coverage.

## Verification

Commands:

```powershell
python -m py_compile scripts\bbi\backtrader\tmp\v6_moneyflow_evolution_experiment.py
python -m unittest scripts\bbi\backtrader\tmp\test_v6_moneyflow_evolution.py -v
python -X utf8 scripts\bbi\backtrader\tmp\v6_moneyflow_evolution_experiment.py
```

Results:

- Compile passed.
- Unit tests passed: 4/4.
- Baseline assertion passed: `baseline_v6` exactly matched v6 `summary.json`.
- Output written to `scripts/bbi/backtrader/tmp/v6_moneyflow_evolution_output`.

## Results

| case | total | annual | max dd | Calmar | trades | blocked |
|---|---:|---:|---:|---:|---:|---:|
| baseline_v6 | 214.56% | 14.68% | -30.61% | 0.4795 | 782 | 0 |
| flow_score_boost_015 | 101.61% | 8.74% | -42.00% | 0.2081 | 800 | 0 |
| flow_net_rank_top70 | 82.45% | 7.45% | -43.87% | 0.1698 | 849 | 44,823 |
| flow_net_ma5_positive | 44.72% | 4.52% | -58.27% | 0.0775 | 734 | 104,539 |
| flow_and_cyq_combo | 28.07% | 3.00% | -47.87% | 0.0627 | 406 | 135,419 |
| flow_big_score_boost_015 | -0.35% | -0.04% | -64.59% | -0.0007 | 885 | 0 |
| flow_big_ma5_positive | -6.08% | -0.75% | -55.53% | -0.0135 | 666 | 104,147 |
| cyq_winner_mid | -21.60% | -2.87% | -63.52% | -0.0451 | 660 | 80,556 |

## Decision

Do not merge any moneyflow/cyq candidate into v6.

Reason:

- No candidate beats `baseline_v6`.
- Every candidate worsens max drawdown materially.
- Hard filters remove too many candidates and break the v6 trade path.
- Score boosts also degrade performance, which suggests these raw moneyflow features do not add stable signal on top of v6.

## Next Step

Do not keep searching by stacking more moneyflow/cyq thresholds.

Recommended next experiment:

1. v6 parameter robustness grid for the winning downtrend filter:
   - MA window: 10/20/30
   - slope window: 5/10/20
   - return window: 10/21/42
2. Cost pressure test:
   - current cost
   - +5 bps slippage
   - +10 bps slippage
3. Walk-forward:
   - train/select on 2018-2021
   - validate on 2022-2024
   - confirm on 2025-2026

Only if v6 remains strong under these checks should it move toward production default.
