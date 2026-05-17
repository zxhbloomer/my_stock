# v6 Downtrend Filter Design

## Context

v6 is isolated from v5. It may copy v5 code as a starting point, but must not read or write v5 output. All v6 artifacts must live under `scripts/bbi/backtrader/v6/output`.

The tmp experiment `scripts/bbi/backtrader/tmp/v5_downtrend_filter_experiment.py` found one useful rule:

```text
close_qfq < MA20
AND MA20_slope_10 < 0
AND ret_21 < 0
```

This is named `early_weakness_downtrend`. In the tmp full-candidate filtering experiment it improved full-period total return from v5 `140.9215%` to `214.5632%`, while max drawdown improved from `-31.1754%` to `-30.6143%`.

## Web Evidence

The rule is consistent with searched trend-following sources:

- Moving-average slope is a trend direction/strength indicator; negative slope indicates downtrend.
- Trend-following systems commonly avoid weak assets or assets below trend averages.
- A price below a moving average with negative recent momentum is a weak-trend state.

## Approaches Considered

### Approach A: Keep v6 as wrapper around v5

Rejected. This would risk reading v5 output or importing v5 runtime paths, violating the isolation requirement.

### Approach B: Copy v5 into v6 and integrate only the winning filter

Selected. This gives isolation, preserves known v5 behavior, and keeps the change small.

### Approach C: Rebuild v6 as refactored modular code

Rejected for this iteration. It would be a large refactor and would make performance differences harder to attribute.

## v6 Design

### Data Preparation

`10_prepare_data.py` remains database-driven like v5, but adds:

- `ma20_qfq`
- `ma20_slope_10`
- `early_weakness_downtrend`

The feature is computed per stock using only historical rows through that row's `trade_date`. v6 backtest uses `signal_date = T-1`, then trades at `T` open, preserving anti-lookahead behavior.

### Backtest

`20_run_backtest.py` extends `PANEL_COLUMNS` to include the v6 downtrend fields.

`score_candidates(signal_panel)` filters candidates where `early_weakness_downtrend == True` when `DOWNTREND_BUY_FILTER_ENABLED` is true.

The filter affects the full candidate set, including both initial buys and add-buys. This is intentional for v6 because the successful tmp case was the full-candidate rule, not initial-only.

New stats:

- `downtrend_filter_enabled`
- `downtrend_filter_candidate_blocks`
- `downtrend_filter_signal_days`
- `downtrend_filter_name`

### Report

`30_generate_report.py` becomes v6-branded and explicitly states:

- v6 is v5 plus early weakness downtrend candidate filtering.
- The output directory is v6-local.
- The filter affects candidate buys/adds, not just first entries.

### Isolation

v6 paths come from `v6/config.py`, using `Path(__file__).parent / "output"`.

No v6 code should read:

- `scripts/bbi/backtrader/v5/output`
- `scripts/bbi/backtrader/tmp/v5_downtrend_filter_output`

v6 may read v1 stats for the existing report comparison pattern only. It must not use v5 output as a baseline during v6 runtime.

## Success Criteria

- v6 has its own `10_prepare_data.py`, `20_run_backtest.py`, `30_generate_report.py`, `config.py`, `README.md`.
- v6 tests prove the downtrend flag and candidate filter behavior.
- `python -m py_compile` passes for v6 scripts.
- `python -m unittest discover scripts\bbi\backtrader\v6 -p "test_*.py" -v` passes.
- v6 backtest writes only under `scripts/bbi/backtrader/v6/output`.
- v6 report HTML is generated from v6 output.
