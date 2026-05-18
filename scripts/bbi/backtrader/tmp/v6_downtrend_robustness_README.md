# v6 Downtrend Robustness Experiment

## Goal

Check whether current v6 downtrend filter parameters are robust or a single lucky point.

Current v6 rule:

```text
close_qfq < MA20
AND MA20_slope_10 < 0
AND ret_21 < 0
```

This experiment stays in `scripts/bbi/backtrader/tmp`, imports v6 functions directly, and writes only tmp output.

## Design

Parameter grid:

- MA window: 10, 20, 30
- slope window: 5, 10, 20
- return window: 10, 21, 42

Total: 27 cases.

Each case uses:

```text
close_qfq < MA{ma}
AND MA{ma}_slope_{slope} < 0
AND ret_{ret} < 0
```

The filter is applied in the same place as v6: after v6 scoring and `MIN_SCORE`, before final candidate sorting. This preserves the corrected tmp/v6 semantics.

## Walk-forward

Selection design:

- Train/select: 2018-2021
- Validate: 2022-2024
- Confirm: 2025-2026

Selection metric:

1. highest train Calmar
2. then higher train total return
3. then less severe train drawdown

## Verification

Commands:

```powershell
python -m py_compile scripts\bbi\backtrader\tmp\v6_downtrend_robustness_experiment.py
python -m unittest scripts\bbi\backtrader\tmp\test_v6_downtrend_robustness.py -v
python -X utf8 scripts\bbi\backtrader\tmp\v6_downtrend_robustness_experiment.py
```

Results:

- Compile passed.
- Unit tests passed: 3/3.
- Current v6 case `ma20_slope10_ret21` exactly matched v6 `summary.json`.
- Output written to `scripts/bbi/backtrader/tmp/v6_downtrend_robustness_output`.

## Full-period Result

Top cases:

| case | total | annual | max dd | Calmar | trades |
|---|---:|---:|---:|---:|---:|
| ma20_slope10_ret42 | 229.32% | 15.31% | -34.08% | 0.4492 | 839 |
| ma20_slope10_ret21 | 214.56% | 14.68% | -30.61% | 0.4795 | 782 |
| ma20_slope5_ret42 | 212.14% | 14.57% | -34.08% | 0.4276 | 992 |
| ma30_slope10_ret21 | 201.97% | 14.12% | -31.80% | 0.4440 | 846 |

Interpretation:

- `ret42` improves full-period return versus current v6, but max drawdown worsens from `-30.61%` to `-34.08%`.
- Drawdown worsening is about 3.47 percentage points, exceeding the 3-point guardrail.
- Current v6 keeps the best Calmar among the top return candidates.

## Walk-forward Result

The train period selected current v6:

| selected | train total | train Calmar | validation total | validation Calmar | confirm total | confirm Calmar |
|---|---:|---:|---:|---:|---:|---:|
| ma20_slope10_ret21 | 181.83% | 0.9666 | -17.01% | -0.2255 | 39.19% | 2.7498 |

Interpretation:

- Current v6 is not merely a bad train-period accident; it is selected by train-period Calmar.
- Validation period remains weak for current v6, but no full-period replacement clears the drawdown guardrail.

## Decision

Do not replace current v6 parameters.

Reason:

- Full-period best by return (`ma20_slope10_ret42`) breaches the drawdown guardrail.
- Walk-forward train selection chooses current v6 (`ma20_slope10_ret21`).
- Current v6 has better risk-adjusted profile than the higher-return ret42 variant.

## Next Step

Run cost pressure tests on:

1. current v6 `ma20_slope10_ret21`
2. full-period high-return challenger `ma20_slope10_ret42`

Cost scenarios:

- current cost
- +5 bps slippage on buys and sells
- +10 bps slippage on buys and sells

If current v6 remains strong under costs, it is a better production candidate than parameter hunting.
