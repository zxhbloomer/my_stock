# tmp_v4 Uptrend BBI Breakout Design

## Hypothesis

The current v6 ranking already prefers stocks with strong BBI persistence and positive medium-term behavior. A stricter right-side trigger may improve realized trades by requiring a fresh BBI reclaim before entry. The expected benefit is fewer weak entries and lower drawdown. The expected risk is missing persistent winners that never dip below BBI before continuing higher.

## Quant Definition

Short BBI breakout uses a 0.5% buffer to reduce noisy one-tick crosses:

```text
prev_close_qfq <= prev_bbi_qfq
close_qfq > bbi_qfq
close_qfq / bbi_qfq - 1 >= 0.005
bbi_qfq / bbi_qfq.shift(5) - 1 > 0
```

Mid BBI:

```text
mid_bbi = (MA5 + MA10 + MA20 + MA60) / 4
mid_bbi_slope_5 = mid_bbi / mid_bbi.shift(5) - 1
```

Uptrend:

```text
close_qfq > MA20 > MA60
MA20 slope over 10 days > 0
MA60 slope over 20 days > 0
ret_63 > max(0, market_ret_60)
close_qfq / rolling_high_252 >= threshold
rps_126 >= threshold
```

## Execution Model

The signal is calculated on the previous trading day. The v6 engine executes buys on the next trading day open, so no same-day close execution is introduced.

## Expert Review

Research expert conclusion: the idea is plausible but vulnerable to false breakouts and overfitting. The design responds by keeping v6 as the base engine, testing only four named variants, and reporting yearly/monthly behavior rather than only final NAV.

Code review scope clarification: this is not a standalone BBI breakout strategy. It is a v6 overlay. v6 candidate ranking, pullback entry thresholds, risk exits, market filters, commissions, and limit-up/down handling remain active.

## Output

The experiment writes all artifacts under:

```text
scripts/bbi/backtrader/tmp/tmp_v4_uptrend_bbi_breakout_output
```

The final HTML report contains:

- Overall comparison with v4, v5, v6, and all variants.
- Annual return comparison.
- Last 36 monthly return comparison.
- Merge recommendation and next steps.
