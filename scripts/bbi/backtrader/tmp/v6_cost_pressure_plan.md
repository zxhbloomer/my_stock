# v6 Cost Pressure Plan

Date: 2026-05-17

## Goal

Run a practical robustness test after the previous experiments showed that new gates and moneyflow/cyq signals do not beat v6. This test asks whether current v6 and the high-return challenger from the downtrend robustness grid survive higher transaction costs.

## Current Evidence

- Uptrend gates did not beat v6.
- Moneyflow/cyq T+1 experiments did not beat v6 and worsened drawdown.
- Downtrend robustness found:
  - current v6: `ma20_slope10_ret21`, total return 214.56%, max drawdown -30.61%.
  - high-return challenger: `ma20_slope10_ret42`, total return 229.32%, max drawdown -34.08%.
  - current v6 was selected by train-period Calmar.

## Tavily Status

Tavily searches for transaction-cost/slippage references were attempted, but the CLI returned a plan usage limit error. No non-Tavily web search was used because the user explicitly required Tavily only.

## Design

Run two downtrend filter cases:

1. `current_v6`: `ma20_slope10_ret21`
2. `ret42_challenger`: `ma20_slope10_ret42`

Run each case under three additional cost scenarios:

1. `cost_0bps`: current v6 commission settings.
2. `cost_5bps`: add 5 bps to every buy and sell transaction amount.
3. `cost_10bps`: add 10 bps to every buy and sell transaction amount.

The extra cost is implemented by monkeypatching v6 `calc_commission(amount, is_buy)` to return:

```text
original_commission(amount, is_buy) + abs(amount) * extra_bps / 10000
```

This keeps signal timing and execution prices unchanged and isolates transaction-cost sensitivity.

## Safety

- Only write to `scripts/bbi/backtrader/tmp/v6_cost_pressure_output`.
- Do not call v6 `main()`.
- Do not modify v4/v5/v6 production files.
- Do not use post-close extra data.
- Restore monkeypatched v6 globals after every run.

## Reporting

The HTML report must include:

- v4/v5/v6 baseline summary.
- Each cost case full-period metrics.
- Annual returns.
- Last 36 monthly returns.
- Recommendation:
  - Merge only if a challenger beats current v6 after costs and does not worsen max drawdown by more than 3 percentage points.
  - Otherwise keep current v6.

