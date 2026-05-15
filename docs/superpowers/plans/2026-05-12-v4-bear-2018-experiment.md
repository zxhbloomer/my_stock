# v4 Bear 2018 Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tmp-only 2018 bear-market experiment runner for v4 and identify parameter sets that improve 2018 returns.

**Architecture:** The runner reads existing v4 parquet/csv outputs, derives market regime features from the market index file, reuses v4-style scoring and trade mechanics in a parameterized loop, then writes result CSV/Markdown under `scripts/bbi/backtrader/tmp/v4_bear_2018_output`.

**Tech Stack:** Python, pandas, existing v4 parquet outputs.

---

### Task 1: Create Experiment Runner

**Files:**
- Create: `scripts/bbi/backtrader/tmp/v4_bear_2018_experiment.py`

- [ ] **Step 1: Implement input loading**

Read:

```python
panel = pd.read_parquet(V4_OUTPUT / "panel.parquet", columns=PANEL_COLUMNS)
market = pd.read_parquet(V4_OUTPUT / "market_index.parquet")
```

Expected columns include `trade_date`, `ts_code`, `open`, `close`, `bbi_qfq`, `pullback_120`, and v4 filter features.

- [ ] **Step 2: Implement market regime features**

Create:

```python
market["ma120"] = market["close"].rolling(120, min_periods=120).mean()
market["ma200"] = market["close"].rolling(200, min_periods=200).mean()
market["bbi_5_20_60_120"] = (
    market["close"].rolling(5).mean()
    + market["close"].rolling(20).mean()
    + market["close"].rolling(60).mean()
    + market["close"].rolling(120).mean()
) / 4
```

- [ ] **Step 3: Implement parameterized 2018 backtest**

Grid:

```python
pullback_thresholds = [-0.05, -0.06, -0.07, -0.08, -0.09, -0.12, -0.15]
market_gates = ["none", "ma120", "ma200", "bbi_5_20_60_120", "ma120_or_bbi"]
```

Use `2018-01-01` to `2018-12-31`.

- [ ] **Step 4: Write output files**

Write:

```text
scripts/bbi/backtrader/tmp/v4_bear_2018_output/results.csv
scripts/bbi/backtrader/tmp/v4_bear_2018_output/summary.md
```

### Task 2: Verify and Compare

**Files:**
- Use: `scripts/bbi/backtrader/tmp/v4_bear_2018_experiment.py`

- [ ] **Step 1: Syntax check**

Run:

```powershell
python -m py_compile scripts\bbi\backtrader\tmp\v4_bear_2018_experiment.py
```

- [ ] **Step 2: Execute experiment**

Run:

```powershell
python scripts\bbi\backtrader\tmp\v4_bear_2018_experiment.py
```

Expected: `results.csv` and `summary.md` are created.

- [ ] **Step 3: Review best row**

Sort by:

```text
total_return_pct desc, max_drawdown_pct desc
```

Compare to v4 2018 baseline:

```text
2018 return: -51.17%
2018 max drawdown: -55.46%
```

- [ ] **Step 4: Compare to v1**

Use `scripts/bbi/backtrader/v1/output/stats_summary.csv` as a single-stock reference only. Report median annual return, median Calmar, and top Calmar row.

