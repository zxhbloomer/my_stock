# BBI tmp experiments

`tmp_vx` means a temporary experiment version, where `x` is an increasing number.

Naming rules:

- Use `tmp_v1_*`, `tmp_v2_*`, ... for new temporary experiments.
- Do not use `v7`, `v8`, ... for experiments unless they are explicitly promoted to an official strategy version.
- Keep official strategy lineage ending at `v6` until a reviewed merge decision changes it.
- Keep experiment scripts, plans, reports, tests, and output directories under this `tmp` directory.

Current temporary experiments:

- `tmp_v1_bear_accel_bbi_*`: bear-market accelerated decline plus BBI reclaim experiment.
- `tmp_v2_bull_pullback_bbi_*`: bull/non-bear pullback plus BBI reclaim experiment.
- `tmp_v5_bear_defensive_quality_*`: bear-probe defensive candidate experiment using low-volatility, quality, dividend, and relative-strength overlays on top of current v6.
