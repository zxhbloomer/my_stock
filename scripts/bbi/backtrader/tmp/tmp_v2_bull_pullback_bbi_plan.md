# tmp_v2 Bull Pullback BBI Experiment Plan

## Scope

- Keep all changes in `scripts/bbi/backtrader/tmp`.
- Do not modify v4, v5, or v6 production strategy files.
- Do not use git.
- Use existing v6 prepared data:
  - `scripts/bbi/backtrader/v6/output/panel.parquet`
  - `scripts/bbi/backtrader/v6/output/market_index.parquet`

## Theory

Tavily search supports a narrower hypothesis than the failed tmp_v2 bear test:

- Pullbacks are commonly framed as buy opportunities only inside an existing uptrend.
- Moving averages can act as support/resistance and confirmation tools.
- Trend trading should follow the dominant trend rather than predict exact bottoms.
- Open-source examples often combine uptrend filters, pullback/oversold states, and moving-average confirmation.

## Expert Review Adjustments

- Test only two variants first:
  - `bull_reclaim`
  - `non_bear_reclaim`
- Defer v6 ranking overlay until the base signal proves useful.
- Use signal-date close only and execute next trading day at `open_qfq`.
- Use prior-day close for exits and stops.

## Rule

- `bull` market:
  - index close > MA120
  - MA120 20-day slope > 0
  - index 252-day drawdown > -15%
- `bear` market:
  - index close < MA120
  - MA120 20-day slope < 0
- `non_bear` market:
  - anything not classified as bear
- Stock quality:
  - `is_eligible`
  - `above_ratio_63 >= 0.55`
  - `above_ratio_126 >= 0.50`
  - `ret_63 >= 0`
  - `hot_money_risk_hits < 2` when available
- Pullback:
  - `pullback_63` between -15% and -4%, or
  - close was below BBI in the prior 10 trading days.
- Confirmation:
  - signal-date `close_qfq` crosses back above `bbi_qfq`.
- Entry:
  - next trading day `open_qfq`.
- Exit:
  - prior-day close below BBI, or
  - prior-day close return <= -8%, or
  - 30 trading-day max hold.

## Output

- Compare v4/v5/v6/tmp_v2 in one HTML report.
- Include annual and recent monthly return tables.
- Include merge recommendation and next steps.

