# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Chinese A-stock quantitative investment research platform built on Microsoft Qlib. End-to-end pipeline: Tushare Pro data collection → Qlib binary format → factor analysis → LightGBM model training → rolling validation → backtesting.

## Environment Setup

```bash
conda env create -f environment.yml
conda activate mystock
pip install -r requirements.txt
```

Configuration in `.env`:
- `TUSHARE_TOKEN` — Tushare Pro API token
- `DATABASE_URL` — PostgreSQL connection (default: `postgresql://root:123456@localhost:5432/my_stock`)

Download base Qlib data (one-time):
```bash
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

## Workflow Pipeline (numbered stages)

Scripts in `scripts/` are organized by stage — run in order:

| Stage | Script | Purpose |
|-------|--------|---------|
| 10 | `scripts/10_数据准备/10_Tushare转Qlib.py` | Convert Tushare PostgreSQL data → Qlib binary |
| 20 | `scripts/20_因子分析/20_IC分析.py` | Information Coefficient factor analysis |
| 30 | `scripts/30_模型训练/30_单模型训练.py [config]` | Train LightGBM model |
| 30 | `scripts/30_模型训练/31_参数优化.py` | Hyperparameter optimization |
| 40 | `scripts/40_模型验证/40_滚动窗口验证.py` | Rolling window out-of-sample validation |

One-click full pipeline: `python scripts/一键运行.py`

View results: `python scripts/result/查看结果.py` or `mlflow ui` (http://localhost:5000)

## Architecture

### Configuration-Driven Workflows

`configs/` contains YAML files that define complete Qlib workflows:
- `workflow_config_lightgbm_Alpha158.yaml` — CSI300 strategy
- `workflow_config_lightgbm_Alpha158_csi500.yaml` — CSI500 strategy
- `workflow_config_lightgbm_BBI.yaml` — BBI indicator strategy

Each YAML specifies: model class/params, dataset (handler + segments), backtest config, and recorder config.

### Custom Factors & Handlers

- `factors/` — Custom Qlib factor definitions using Qlib expression language (e.g., `Mean($close, N)`)
- `handlers/` — Custom `DataHandlerLP` subclasses extending Alpha158 with additional features

Qlib expression syntax for factors: `$field` references raw data; operators like `Mean()`, `Std()`, `Ref()` build derived features.

### Data Flow

```
Tushare Pro API → PostgreSQL (my_stock DB) → scripts/10 converter → ~/.qlib/qlib_data/ (binary) → Qlib handlers → model training
```

The `data/` module handles Tushare collection into PostgreSQL. Key tables documented in `docs/数据库表结构清单_带注释.md`.

### MLflow Tracking

All experiments auto-logged to `mlruns/`. Recorders capture: predictions, model artifacts, backtest metrics (IC, ICIR, Sharpe, max drawdown).

## Key Files

- `docs/参数优化使用指南.md` — Parameter optimization workflow
- `docs/滚动窗口验证使用说明.md` — Rolling validation guide
- `docs/tushare/接口清单.md` — Complete Tushare Pro API catalog (239 interfaces)
- `scripts/run/run_gui.py` — Tkinter GUI for data management tasks


docker中保存了tushare的数据，D:\2025_project\00_docker\postgresql\docker-compose.yml

## 回测数据时序规则（防未来数据泄露）

**核心规则：所有盘后数据必须使用 T-1 日数据，禁止使用当日数据做当日决策。**

### 原因

Tushare 的 moneyflow（资金流向）、cyq_perf（筹码分布）等数据在 T 日收盘后才能获取。
回测中若直接用 T 日数据触发 T 日收盘买入，属于未来数据泄露（look-ahead bias），会虚高回测收益。

### 规则

| 数据类型 | 来源表 | 处理方式 |
|---------|--------|---------|
| OHLCV、BBI、MA | stk_factor_pro | 当日数据可用（价格是已知的） |
| moneyflow 资金流向 | moneyflow | **shift(1)** — 使用前一日数据 |
| cyq_perf 筹码分布 | cyq_perf | **shift(1)** — 使用前一日数据 |
| 其他盘后衍生数据 | 任意 | **shift(1)** — 默认使用前一日数据 |

### 实现位置

在 `10_prepare_data.py` 的 parquet 生成阶段做 shift，策略代码无需修改：

```python
# 盘后数据必须 shift(1)，避免未来数据泄露
# T 日的 moneyflow/cyq_perf 在收盘后才可得，只能用于 T+1 日决策
df['net_mf_amount'] = df['net_mf_amount'].shift(1)
df['winner_rate']   = df['winner_rate'].shift(1)
```