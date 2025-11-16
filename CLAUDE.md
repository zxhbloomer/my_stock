# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A quantitative investment project for Chinese A-shares built on Microsoft Qlib framework. Uses LightGBM models with Alpha158 technical indicators for stock prediction and backtesting.

## Environment Setup

**Python Environment**: Python 3.8 with conda
**Environment Name**: `mystock`

```bash
# Create environment
conda env create -f environment.yml

# Activate environment
conda activate mystock

# Initialize Qlib and download data
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

**Important**: Always activate the `mystock` conda environment before running any commands. The Python executable path is:
```
C:\Users\Administrator\miniconda3\envs\mystock\python.exe
```

## Core Commands

### Running Workflows

```bash
# Run complete workflow with default config
python scripts/30_运行工作流.py

# Run with specific config
python scripts/30_运行工作流.py configs/workflow_config_lightgbm_Alpha158_csi500.yaml

# View backtest results and charts
python view_results.py

# Generate Chinese-labeled charts
python view_charts.py
```

### MLflow Integration

All experiments are tracked in `mlruns/`:
```bash
# View experiment results in MLflow UI
mlflow ui
# Access at http://localhost:5000
```

## Architecture

### Workflow Pipeline

The workflow follows Qlib's standard pipeline:

1. **Initialization** (`qlib.init`)
   - Loads data from `~/.qlib/qlib_data/cn_data`
   - Region: `cn` (China)

2. **Model Training** (`scripts/30_运行工作流.py`)
   - Model: LightGBM (`qlib.contrib.model.gbdt.LGBModel`)
   - Dataset: DatasetH with Alpha158 features
   - Training period: 2008-2014
   - Validation period: 2015-2016
   - Test period: 2017-2020

3. **Prediction & Analysis**
   - Generates signals: `SignalRecord`
   - Analyzes signal quality: `SigAnaRecord`
   - Backtests portfolio: `PortAnaRecord`

4. **Backtest Configuration**
   - Strategy: TopkDropoutStrategy (top 50 stocks, drop 5)
   - Initial capital: 100M CNY
   - Benchmark: SH000300 (CSI 300) or SH000905 (CSI 500)
   - Trading costs: open 0.05%, close 0.15%, min 5 CNY

### Directory Structure

```
my_stock/
├── configs/              # YAML workflow configurations
│   ├── workflow_config_lightgbm_Alpha158.yaml          # CSI300 strategy
│   └── workflow_config_lightgbm_Alpha158_csi500.yaml   # CSI500 strategy
├── utils/                # Utility modules
│   └── chinese_charts.py # Chinese-labeled chart functions
├── mlruns/               # MLflow experiment tracking (auto-generated)
├── scripts/              # Analysis and utility scripts
│   ├── 00_Tushare转Qlib.py      # Data conversion from Tushare
│   ├── 10_检查环境.py            # Environment validation
│   ├── 20_IC分析.py              # Factor IC analysis
│   ├── 21_使用IC结果.py          # IC results utilities
│   ├── 22_训练Top因子模型.py     # Train with top factors
│   ├── 30_运行工作流.py          # Main workflow execution script
│   └── 参数优化_改进版.py        # LightGBM parameter tuning
├── docs/                 # Documentation and design docs
├── view_results.py       # Results analysis and chart generation
└── view_charts.py        # Chinese chart visualization
```

### Key Configuration Files

**Workflow Config Structure** (`configs/*.yaml`):
- `qlib_init`: Data provider and region settings
- `market`: Stock universe (csi300/csi500)
- `benchmark`: Reference index (SH000300/SH000905)
- `data_handler_config`: Time periods and instruments
- `task.model`: LightGBM parameters
- `task.dataset`: DatasetH with Alpha158 handler
- `task.record`: SignalRecord, SigAnaRecord, PortAnaRecord

### Results Loading Pattern

Results are stored in MLflow recorder structure:

```python
from qlib.workflow import R

# Load latest backtest
recorder = R.get_recorder(recorder_id=rid, experiment_name="backtest_analysis")

# Access results
pred_df = recorder.load_object("pred.pkl")
report_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
positions = recorder.load_object("portfolio_analysis/positions_normal_1day.pkl")
analysis_df = recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")
```

### Chinese Chart Utilities

`utils/chinese_charts.py` provides wrapper functions with Chinese labels:
- `score_ic_graph_cn()`: IC analysis with Chinese descriptions
- `model_performance_graph_cn()`: Model performance charts
- `report_graph_cn()`: Portfolio report visualization
- `risk_analysis_graph_cn()`: Risk metrics analysis
- `show_all_charts_cn()`: Display all charts at once

These wrap official Qlib functions while adding Chinese commentary.

## Data Integration Notes

The `doc/` directory contains Tushare Pro API documentation for potential future data source integration. Currently, the project uses Qlib's official data provider.

## Windows-Specific Notes

- Scripts use `.bat` files for Windows environment
- Use forward slashes or escaped backslashes in Python paths
- MLflow experiments stored in `mlruns/` with Windows-compatible paths
- Chinese font handling: `plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']`

## MCP Database Configuration

MySQL connection (if using MCP):
- Host: 127.0.0.1:3306
- Database: scm_tenant_20250519_001
- User: root / Password: 123456

PostgreSQL connection (if using MCP):
- Host: 127.0.0.1:5432
- Database: scm_tenant_20250519_001
- User: root / Password: 123456

## Key Metrics

**Backtest Metrics** (from `analysis_df`):
- `annualized_return`: Annualized return rate
- `information_ratio`: Risk-adjusted return (IR > 1.0 is excellent)
- `max_drawdown`: Maximum drawdown (MDD)
- `mean`, `std`: Mean return and volatility

**IC Metrics** (Information Coefficient):
- Pearson IC: Linear correlation between predictions and returns
- Rank IC (Spearman): Rank correlation
- IC mean > 0.01: Good, IC mean > 0.03: Excellent

**Analysis Categories**:
- `excess_return_without_cost`: Returns before trading costs
- `excess_return_with_cost`: Net returns after trading costs

**Qlib的数据目录**
- windows环境 D:\Data\my_stock


D:\2025_project\99_quantify\python\my_stock\docs\数据库表结构清单_带注释.md