# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python research platform for China A-share quantitative strategies. Core data collection and database sync code lives in `data/`. Qlib workflow configuration is in `configs/`, with custom factors in `factors/` and custom handlers in `handlers/`. Strategy and pipeline scripts are under `scripts/`; the active BBI rotation workflow is `scripts/bbi/backtrader/v4_plan_1/`. Shared helpers live in `utils/`. Documentation and design notes are in `docs/`, while generated experiment artifacts are written to `mlruns/` and strategy output folders.

## Build, Test, and Development Commands

Create the environment:

```powershell
conda env create -f environment.yml
conda activate mystock
pip install -r requirements.txt
```

Run the current BBI workflow:

```powershell
cd scripts/bbi/backtrader/v4_plan_1
python -X utf8 10_prepare_data.py
python -X utf8 20_run_backtest.py
python -X utf8 30_generate_report.py
```

Run the Qlib workflow examples from the repository root:

```powershell
python scripts/10_数据准备/10_Tushare转Qlib.py
python scripts/30_模型训练/30_单模型训练.py configs/workflow_config_lightgbm_Alpha158.yaml
mlflow ui
```

## Coding Style & Naming Conventions

Use Python 3.8-compatible code. Follow existing script naming: numbered pipeline files such as `10_prepare_data.py`, `20_run_backtest.py`, and `30_generate_report.py`. Prefer clear snake_case for functions, variables, and filenames unless matching an existing Chinese workflow path. Keep configuration values in `config.py` or YAML files rather than hardcoding strategy parameters. Use `python -X utf8` for scripts that print Chinese text on Windows.

## Testing Guidelines

There is no formal test suite yet. Validate changes by running the smallest affected pipeline step, then the full BBI sequence when touching strategy logic or data preparation. For experimental work, place temporary checks in `scripts/bbi/backtrader/tmp/` and keep generated output out of commits unless it is intentionally documented.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit style, for example `feat(bbi): ...`, `fix(minishare): ...`, and `docs(v4_plan_1): ...`. Keep commits scoped and describe the affected module. Pull requests should include a summary, commands run, data assumptions, and screenshots or report paths when changing HTML reports.

## Security & Configuration Tips

Do not commit `.env`, Tushare tokens, database credentials, or local PostgreSQL paths. Use `.env.example` or `.env.template` for placeholders. Preserve the anti-lookahead rule: any post-close data such as `moneyflow` or `cyq_perf` must be shifted before being used for trading decisions.
