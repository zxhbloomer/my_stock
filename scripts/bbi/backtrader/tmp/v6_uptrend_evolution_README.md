# v6 Uptrend Evolution Progress

## 2026-05-17

- Started from user goal: improve returns by evolving v6 so buys require a real uptrend.
- Used Tavily search to verify programmable uptrend concepts: higher highs/higher lows, rising moving averages, Minervini trend template, Weinstein Stage 2, market breadth, and momentum crash risk in bear markets.
- Reviewed Tushare interface list. Relevant future data candidates: `moneyflow`, `cyq_perf`, `daily_basic`, industry/board flows. Current experiment intentionally avoids post-close unshifted new data and uses existing v6 panel fields.
- Quant expert review completed. Recommendation: run three fixed variants and compare against v4, v5, and v6 with annual/monthly breakdown.
- Implementation scope: isolated tmp experiment, no git operations, no production v6 code changes.

## Run Result

- Command: `python -X utf8 scripts\bbi\backtrader\tmp\v6_uptrend_evolution_experiment.py`
- Full variant run completed, but first report generation failed on an HTML template set-literal typo after all three backtests had already written outputs.
- Fixed report generation and regenerated report from existing completed variant outputs.
- Report: `scripts/bbi/backtrader/tmp/v6_uptrend_evolution_output/report.html`

| Strategy | Final NAV | Total Return | Annual Return | Max Drawdown | Calmar |
|---|---:|---:|---:|---:|---:|
| v4 | 1,090,102.33 | 118.02% | 9.76% | -46.31% | 0.21 |
| v5 | 1,204,607.39 | 140.92% | 11.08% | -31.18% | 0.36 |
| v6 | 1,572,816.08 | 214.56% | 14.68% | -30.61% | 0.48 |
| price_trend_only | 1,032,936.45 | 106.59% | 9.06% | -44.76% | 0.20 |
| price_plus_relative_strength | 1,265,590.93 | 153.12% | 11.74% | -52.59% | 0.22 |
| market_regime_adaptive | 1,112,677.69 | 122.54% | 10.03% | -43.20% | 0.23 |

Recommendation: do not merge this uptrend-only buy filter into v6. It reduced final NAV versus v6 and worsened drawdown/Calmar.
