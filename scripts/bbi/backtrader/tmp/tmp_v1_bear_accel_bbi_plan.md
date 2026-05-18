# tmp_v1 Bear Acceleration BBI Experiment Plan

## Scope

- Keep all changes in `scripts/bbi/backtrader/tmp`.
- Do not modify v4, v5, or v6 production strategy files.
- Do not use git.
- Use existing v6 prepared data:
  - `scripts/bbi/backtrader/v6/output/panel.parquet`
  - `scripts/bbi/backtrader/v6/output/market_index.parquet`
- Compare against existing v4/v5/v6 outputs.

## Expert Roles

- Strategy design expert: checks whether the bear acceleration and BBI reclaim rule is economically coherent.
- Data QA expert: checks T+1 execution, no lookahead, and post-close feature handling.
- Engineering reviewer: checks tmp isolation, testability, and report clarity.
- Results reviewer: checks whether comparison supports merge or only further research.

## Variants

1. `bear_only`: apply the acceleration/exhaustion + BBI reclaim buy rule only when market regime is bear.
2. `all_market`: apply the same stock rule in every market regime.

## Rule

- Market bear:
  - market close below MA120 and MA120 20-day slope below zero.
  - 252-day drawdown is reported as a diagnostic, not used as a bear trigger.
- Stock setup:
  - recent downside acceleration appeared within the last 10 trading days;
  - 21-day return <= -12%;
  - short-term slope has started to improve, or close has stopped making fresh 5-day lows.
- Confirmation:
  - `close_qfq` crosses above `bbi_qfq` on signal date.
  - Buy on the next trading day's open.
- Risk:
  - sell on the next trading day after a close crossing below BBI, prior-close -8% stop signal, or 30 trading-day max hold.

## Verification

- Unit tests for signal and regime helpers.
- Compile the tmp experiment.
- Run both variants.
- Baseline compare with v4/v5/v6 summaries.
- Generate HTML report with annual and monthly tables.

## Tavily Status

- Tavily search was attempted for finance/literature/GitHub terms.
- The session returned plan-limit errors, so no external Tavily evidence can be added unless quota becomes available.

